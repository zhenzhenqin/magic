import asyncio
import base64
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from secrets import token_urlsafe

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import DEEPSEEK_COMPACT_BODY_BYTES, DEEPSEEK_ENDPOINT, DEEPSEEK_VISION_MODEL, Settings
from app.models.ai import AiCallBudget
from app.services.ai_prompt import CONSENT_VERSION, DEEPSEEK_CONSENT_VERSION, DEEPSEEK_PRIVACY_URL
from app.services.ai_provider import DeepSeekVisionProvider, ProviderError, build_provider, prepare_photo
from tests.support import isolated_settings, migrate
from tests.test_ai_jobs import JOBS, attempts, env, new_job, photo, worker
from tests.test_ai_provider import food, response, result
from tests.test_identity import API, bearer, signed_in
from tests.test_phase41 import qwen_settings, spent


def deepseek_settings(app, limit):
    settings = app.state.settings
    settings.ai_provider = "deepseek"
    settings.ai_base_url = DEEPSEEK_ENDPOINT
    settings.ai_model = DEEPSEEK_VISION_MODEL
    settings.ai_api_key = SecretStr(token_urlsafe(42))
    settings.ai_deepseek_cumulative_limit = limit
    return settings


@pytest.fixture
def deepseek(tmp_path):
    return isolated_settings(tmp_path / "vision-test.db", ai_enabled=True, ai_provider="deepseek",
                             ai_base_url=DEEPSEEK_ENDPOINT, ai_model=DEEPSEEK_VISION_MODEL,
                             ai_max_output_tokens=1024, ai_api_key=token_urlsafe(40))


def analyze(settings, handle, images=None):
    client = DeepSeekVisionProvider(settings, httpx.MockTransport(handle))
    return asyncio.run(client.analyze(images or [b"sample"]))


@pytest.mark.parametrize("images", [[b"one"], [b"one", b"two"]])
def test_deepseek_sends_official_vision_and_json_parameters(deepseek, images):
    def handle(request):
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        assert request.method == "POST" and request.headers["authorization"].startswith("Bearer ")
        body = json.loads(request.content)
        assert body["model"] == "deepseek-flash" and body["stream"] is False and body["max_tokens"] == 1024
        assert body["thinking"] == {"type": "disabled"} and body["response_format"] == {"type": "json_object"}
        assert "enable_thinking" not in body and "tools" not in body
        assert "JSON" in body["messages"][0]["content"]
        image_urls = [entry["image_url"]["url"] for entry in body["messages"][1]["content"] if entry["type"] == "image_url"]
        assert image_urls == ["data:image/jpeg;base64," + base64.b64encode(image).decode() for image in images]
        assert deepseek.ai_api_key.get_secret_value() not in request.content.decode()
        return response(result(food()))

    answer = analyze(deepseek, handle, images)
    assert answer.result.foods[0].food_name == "白米饭"
    assert (answer.usage.input_tokens, answer.usage.output_tokens) == (181, 125)
    assert isinstance(build_provider(deepseek), DeepSeekVisionProvider)


def test_compact_deepseek_bounds_request_before_network(deepseek):
    deepseek.ai_max_images = 1
    deepseek.ai_deepseek_compact_request = True
    calls = []

    def handle(request):
        calls.append(len(request.content))
        return response(result(food()))

    photo_path = Path(__file__).resolve().parents[2] / "frontend/src/assets/food/croissant.webp"
    assert analyze(deepseek, handle, [prepare_photo(photo_path, 1024)]).result.status == "recognized"
    assert 0 < calls[0] <= DEEPSEEK_COMPACT_BODY_BYTES
    for images in ([b"one", b"two"], [b"x" * DEEPSEEK_COMPACT_BODY_BYTES]):
        with pytest.raises(ProviderError, match="ai_image_invalid") as error:
            analyze(deepseek, handle, images)
        assert not error.value.sent
    assert len(calls) == 1


@pytest.mark.parametrize(("content", "finish"), [
    ("", "stop"), (None, "stop"), ('{"status":', "length"),
    ('{"schema_version":"1","status":"recognized","foods":[],"warnings":[]}', "stop"),
])
def test_deepseek_empty_truncated_and_bad_schema_keep_known_usage(deepseek, content, finish):
    reply = httpx.Response(200, json={"id": "fixture", "choices": [{"finish_reason": finish, "message": {"content": content}}],
                                     "usage": {"prompt_tokens": 19, "completion_tokens": 3}})
    with pytest.raises(ProviderError, match="ai_invalid_result") as error:
        analyze(deepseek, lambda _: reply)
    assert error.value.sent and not error.value.retryable
    assert (error.value.usage.input_tokens, error.value.usage.output_tokens) == (19, 3)


@pytest.mark.parametrize(("status", "code", "retryable"), [
    (401, "ai_provider_auth", False), (402, "ai_provider_balance", False), (429, "ai_rate_limited", True),
    (503, "ai_result_unknown", False), (302, "ai_provider_rejected", False),
])
def test_deepseek_http_failure_never_redirects_or_repeats_on_unknown(deepseek, status, code, retryable):
    calls = []
    def handle(request):
        calls.append(request.url)
        return httpx.Response(status, headers={"Location": "https://different.example.test", "Retry-After": "3"})

    with pytest.raises(ProviderError, match=code) as error:
        analyze(deepseek, handle)
    assert len(calls) == 1 and error.value.sent and error.value.retryable == retryable


@pytest.mark.parametrize("url", [
    "http://api.deepseek.com", "https://api.deepseek.com:443", "https://api.deepseek.com/v1",
    "https://proxy.example.test", "https://api.deepseek.com.evil.example", "https://api.deepseek.com?test=1",
])
def test_deepseek_official_origin_validated_both_at_config_and_send(deepseek, url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret=token_urlsafe(48), ai_provider="deepseek", ai_base_url=url)
    deepseek.ai_base_url = url
    with pytest.raises(ProviderError, match="ai_configuration_changed") as error:
        analyze(deepseek, lambda _: pytest.fail("Unexpected HTTP call"))
    assert not error.value.sent


def test_deepseek_consent_and_provider_switch_require_a_new_job(env):
    app, client = env
    qwen_settings(app, 1)
    auth = bearer(signed_in(client))
    image = photo(client, auth)
    original = new_job(client, auth, [image]).json()["id"]
    deepseek_settings(app, 1)
    disclosure = client.get(API + "/ai/capabilities", headers=auth).json()
    assert disclosure["provider"] == "deepseek" and disclosure["privacy_url"] == DEEPSEEK_PRIVACY_URL
    assert disclosure["consent_version"] == DEEPSEEK_CONSENT_VERSION != CONSENT_VERSION
    assert new_job(client, auth, [image]).json()["error"]["code"] == "ai_consent_required"
    assert worker(app).claim() is None
    old = client.get(JOBS + "/" + original, headers=auth).json()
    assert old["error_code"] == "ai_configuration_changed" and not old["can_retry"]
    assert not attempts(app, original)
    renewed = new_job(client, auth, [image], consent_version=DEEPSEEK_CONSENT_VERSION)
    assert renewed.status_code == 202 and renewed.json()["id"] != original


def test_deepseek_cumulative_default_zero_and_daily_usage_spans_real_providers(env):
    app, client = env
    qwen_settings(app, 3)
    auth = bearer(signed_in(client))
    image = photo(client, auth)
    assert new_job(client, auth, [image]).status_code == 202
    assert asyncio.run(worker(app).process_once()) and spent(app) == 1
    default = app.state.settings.ai_deepseek_cumulative_limit
    settings = deepseek_settings(app, default)
    assert default == 0
    assert new_job(client, auth, [image], consent_version=DEEPSEEK_CONSENT_VERSION).json()["error"]["code"] == "ai_cumulative_limit"
    settings.ai_deepseek_cumulative_limit = 1
    settings.ai_global_daily_limit = 1
    assert new_job(client, auth, [image], consent_version=DEEPSEEK_CONSENT_VERSION).json()["error"]["code"] == "ai_quota"
    settings.ai_global_daily_limit = 3
    first = new_job(client, auth, [image], consent_version=DEEPSEEK_CONSENT_VERSION)
    assert first.status_code == 202
    assert asyncio.run(worker(app).process_once())
    assert new_job(client, auth, [image], consent_version=DEEPSEEK_CONSENT_VERSION).json()["error"]["code"] == "ai_cumulative_limit"
    with app.state.session_factory() as db:
        assert db.get(AiCallBudget, "qwen").spent == db.get(AiCallBudget, "deepseek").spent == 1


@pytest.mark.parametrize(("transport_error", "charged"), [(httpx.ConnectTimeout, 0), (httpx.ReadTimeout, 1)])
def test_deepseek_transport_accounting_keeps_unknown_and_refunds_precise_pre_send(env, transport_error, charged):
    app, client = env
    settings = deepseek_settings(app, 1)
    settings.ai_max_attempts = 1
    auth = bearer(signed_in(client))
    identifier = new_job(client, auth, [photo(client, auth)], consent_version=DEEPSEEK_CONSENT_VERSION).json()["id"]
    def handle(_):
        raise transport_error("fixture")

    service = worker(app, DeepSeekVisionProvider(settings, httpx.MockTransport(handle)))
    assert asyncio.run(service.process_once())
    assert attempts(app, identifier)[0].status == ("unknown" if charged else "not_sent")
    with app.state.session_factory() as db:
        assert db.get(AiCallBudget, "deepseek").spent == charged and db.get(AiCallBudget, "qwen").spent == 0


def test_upgrade_adds_deepseek_preserving_existing_qwen_count(settings):
    migrate(settings, "0005_ai_processing_context")
    with closing(sqlite3.connect(settings.db_url.database)) as db:
        db.execute("UPDATE ai_call_budgets SET spent = 4 WHERE provider = 'qwen'")
        db.commit()
    migrate(settings)
    with closing(sqlite3.connect(settings.db_url.database)) as db:
        assert dict(db.execute("SELECT provider, spent FROM ai_call_budgets")) == {"qwen": 4, "deepseek": 0}
