import asyncio
import base64
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from typing import Protocol

import httpx
from PIL import Image
from pydantic import ValidationError

from app.ai_schemas import Recognition
from app.core.config import Settings
from app.services.ai_prompt import SYSTEM_PROMPT

MAX_IMAGE_BYTES = 640 * 1024
MAX_RESPONSE_BYTES = 96 * 1024


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class Analysis:
    result: Recognition
    usage: Usage = Usage()


class ProviderError(Exception):
    def __init__(self, code: str, *, sent: bool = True, retryable: bool = False,
                 usage: Usage = Usage(), retry_after: int = 0):
        super().__init__(code)
        self.code, self.sent, self.retryable = code, sent, retryable
        self.usage, self.retry_after = usage, retry_after


class FoodRecognitionProvider(Protocol):
    async def analyze(self, images: list[bytes]) -> Analysis: ...


def prepare_photo(path, edge: int) -> bytes:
    with Image.open(path, formats=["WEBP"]) as source:
        source.thumbnail((edge, edge), Image.Resampling.LANCZOS)
        with Image.new("RGB", source.size, "white") as rgb:
            if "A" in source.getbands():
                rgb.paste(source, mask=source.getchannel("A"))
            else:
                rgb.paste(source)
            with BytesIO() as output:
                rgb.save(output, "JPEG", quality=80)
                size = output.tell()
                if size > MAX_IMAGE_BYTES:
                    raise ProviderError("ai_image_invalid", sent=False)
                return output.getvalue()


def token_count(value):
    return value if type(value) is int and 0 <= value <= 10_000_000 else None


def request_id(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value) else None


def unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("Duplicate JSON keys")
    return result


class QwenVisionProvider:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    async def analyze(self, images: list[bytes]) -> Analysis:
        settings = self.settings
        if not settings.ai_available or settings.ai_provider != "qwen" or not settings.ai_api_key:
            raise ProviderError("ai_unavailable", sent=False)
        content = [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")}}
            for data in images
        ]
        content.append({"type": "text", "text": "联合分析所选照片，返回食物记录 JSON。"})
        body = {
            "model": settings.ai_model, "stream": False, "enable_thinking": False,
            "max_tokens": settings.ai_max_output_tokens, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}],
        }
        timeout = httpx.Timeout(settings.ai_timeout_seconds, connect=min(8, settings.ai_timeout_seconds))
        usage = Usage()
        secret = settings.ai_api_key.get_secret_value()
        try:
            async with asyncio.timeout(settings.ai_timeout_seconds), httpx.AsyncClient(
                timeout=timeout, trust_env=False, follow_redirects=False, transport=self.transport,
            ) as client:
                async with client.stream(
                    "POST", settings.ai_base_url + "/chat/completions", json=body,
                    headers={"Authorization": "Bearer " + secret},
                ) as response:
                    upstream = response.headers.get("x-request-id", "")
                    usage = Usage(request_id=request_id(upstream) if secret not in upstream else None)
                    code = response.status_code
                    if code == 429:
                        delay = response.headers.get("retry-after", "")
                        wait = int(delay) if re.fullmatch(r"[0-9]{1,4}", delay) else 30
                        raise ProviderError("ai_rate_limited", retryable=True, retry_after=wait, usage=usage)
                    if code in (401, 403):
                        raise ProviderError("ai_provider_auth", usage=usage)
                    if code == 408 or code >= 500:
                        raise ProviderError("ai_result_unknown", usage=usage)
                    if code != 200:
                        raise ProviderError("ai_provider_rejected", usage=usage)
                    raw = bytearray()
                    async for part in response.aiter_bytes(chunk_size=8192):
                        raw.extend(part)
                        if len(raw) > MAX_RESPONSE_BYTES:
                            raise ProviderError("ai_invalid_result", usage=usage)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            raise ProviderError("ai_before_send", sent=False, retryable=True) from None
        except (TimeoutError, httpx.TransportError):
            raise ProviderError("ai_result_unknown", usage=usage) from None
        try:
            envelope = json.loads(raw, object_pairs_hook=unique_object)
            counts = envelope.get("usage") or {}
            upstream = request_id(envelope.get("id")) or ""
            usage = Usage(token_count(counts.get("prompt_tokens")), token_count(counts.get("completion_tokens")),
                          usage.request_id or (upstream if upstream and secret not in upstream else None))
            choice = envelope["choices"][0]
            if choice["finish_reason"] != "stop":
                raise ValueError("Incomplete result")
            data = json.loads(choice["message"]["content"], parse_float=Decimal, object_pairs_hook=unique_object)
            validated = Recognition.model_validate(data).normalize_estimates()
            if secret in validated.model_dump_json():
                raise ValueError("Result contains a credential")
            return Analysis(validated, usage)
        except (ValidationError, ValueError, KeyError, IndexError, TypeError, AttributeError, RecursionError):
            raise ProviderError("ai_invalid_result", usage=usage) from None


class FakeVisionProvider:
    """Deterministic, offline examples for explicitly simulated runs."""

    async def analyze(self, images: list[bytes]) -> Analysis:
        defaults = dict(weight_g=None, calories_kcal=None, protein_g=None, carbohydrates_g=None, fat_g=None)
        foods = [
            dict(defaults, food_name="番茄炒蛋", category="其他", weight_g=180, calories_kcal=230,
                 protein_g=12, carbohydrates_g=9, fat_g=16, uncertainty="用油量根据常见做法估算"),
            dict(defaults, food_name="白米饭", category="主食", weight_g=150, calories_kcal=174,
                 protein_g=4, carbohydrates_g=38, fat_g=0.5, uncertainty="份量根据图片估算"),
        ]
        return Analysis(Recognition(schema_version="1", status="recognized", foods=foods, warnings=[]))


def build_provider(settings: Settings) -> FoodRecognitionProvider:
    if not settings.ai_available:
        raise ProviderError("ai_unavailable", sent=False)
    if settings.ai_provider == "fake" and settings.app_env != "production":
        return FakeVisionProvider()
    return QwenVisionProvider(settings)
