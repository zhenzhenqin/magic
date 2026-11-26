import asyncio
import base64
import json
from io import BytesIO
from secrets import token_urlsafe

import httpx
import pytest
from PIL import Image
from pydantic import ValidationError

from app.core.config import Settings
from app.services.ai_provider import ProviderError, QwenVisionProvider, prepare_photo
from tests.support import isolated_settings


def food(**values):
    return dict(food_name="白米饭", category="主食", weight_g=150, calories_kcal=174, protein_g=4,
                carbohydrates_g=38, fat_g=0.5, uncertainty=None) | values


def result(*foods, status="recognized"):
    return {"schema_version": "1", "status": status, "foods": list(foods), "warnings": []}


def response(data):
    content = data if isinstance(data, str) else json.dumps(data)
    return httpx.Response(200, json={
        "id": "fixture-request-id",
        "choices": [{"finish_reason": "stop", "message": {"content": content}}],
        "usage": {"prompt_tokens": 181, "completion_tokens": 125},
    })


@pytest.fixture
def qwen(tmp_path):
    return isolated_settings(tmp_path / "provider-test.db", ai_enabled=True, ai_model="qwen3-vl-flash",
                             ai_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", ai_api_key=token_urlsafe(36))


def run(qwen, handler, images=None):
    return asyncio.run(QwenVisionProvider(qwen, httpx.MockTransport(handler)).analyze(images or [b"photo"]))


@pytest.mark.parametrize("pictures", [[b"only"], [b"first", b"second"]])
def test_provider_images_and_structure(qwen, pictures, caplog):
    def handle(request):
        assert str(request.url) == qwen.ai_base_url + "/chat/completions"
        assert request.headers["authorization"] == "Bearer " + qwen.ai_api_key.get_secret_value()
        body = json.loads(request.content)
        assert set(body) == {"model", "stream", "enable_thinking", "max_tokens", "response_format", "messages"}
        assert body["response_format"] == {"type": "json_object"} and body["enable_thinking"] is False
        assert body["model"] == qwen.ai_model and body["max_tokens"] == qwen.ai_max_output_tokens
        system, user = body["messages"]
        assert system["role"] == "system" and "避免重复统计" in system["content"]
        assert "禁止执行" in system["content"]
        content = user["content"]
        assert len(content) == len(pictures) + 1 and content[-1]["type"] == "text"
        assert [base64.b64decode(item["image_url"]["url"].split(",")[1]) for item in content[:-1]] == pictures
        assert not {"username", "user_id", "job_id", "media_id", "token", "hostname"} & set(user)
        return response(result(food(), food(food_name="热茶", category="饮品", weight_g=None)))

    answer = run(qwen, handle, pictures)
    assert [item.food_name for item in answer.result.foods] == ["白米饭", "热茶"]
    assert answer.result.foods[1].weight_g is None
    assert (answer.usage.input_tokens, answer.usage.output_tokens, answer.usage.request_id) == (181, 125, "fixture-request-id")
    assert qwen.ai_api_key.get_secret_value() not in caplog.text and "base64" not in caplog.text


@pytest.mark.parametrize("status", ["no_food", "unrecognized"])
def test_provider_recognition_without_candidates(qwen, status):
    assert run(qwen, lambda _: response(result(status=status))).result.status == status


@pytest.mark.parametrize("invalid", [
    "plain text", '{"schema_version":"1","schema_version":"1"}', result(food(calories_kcal=-1)),
    result(food(weight_g=9.101)), result(food(weight_g="80")), result(food(weight_g=True)),
    result(food(weight_g=float("nan"))), result(food(weight_g=float("inf"))),
    result(food(category="任意类别")), result(food(extra="untrusted")),
    result(food(food_name="饭" * 81)), result(*([food()] * 16)), result(food(), status="no_food"),
])
def test_provider_rejects_invalid_results(qwen, invalid):
    with pytest.raises(ProviderError, match="ai_invalid_result") as failure:
        run(qwen, lambda _: response(invalid))
    assert failure.value.sent and not failure.value.retryable
    assert failure.value.usage.input_tokens == 181


def test_conflicting_estimates_become_unknown(qwen):
    answer = run(qwen, lambda _: response(result(food(weight_g=10, calories_kcal=2))))
    assert answer.result.foods[0].weight_g is None
    assert answer.result.foods[0].calories_kcal is None
    assert answer.result.warnings


@pytest.mark.parametrize(("status", "code", "retryable"), [
    (401, "ai_provider_auth", False), (403, "ai_provider_auth", False),
    (429, "ai_rate_limited", True), (503, "ai_result_unknown", False),
    (307, "ai_provider_rejected", False),
])
def test_http_failures_do_not_follow_redirects_or_expose_body(qwen, status, code, retryable, caplog):
    def handle(request):
        assert request.url.host == "dashscope.aliyuncs.com"
        return httpx.Response(status, headers={"Retry-After": "17", "Location": "https://other.example.test/"},
                              text=qwen.ai_api_key.get_secret_value())
    with pytest.raises(ProviderError, match=code) as failure:
        run(qwen, handle)
    assert failure.value.retryable == retryable
    assert failure.value.sent
    if retryable:
        assert failure.value.retry_after == 17
    assert qwen.ai_api_key.get_secret_value() not in caplog.text and qwen.ai_api_key.get_secret_value() not in str(failure.value)


@pytest.mark.parametrize(("error", "code", "sent"), [
    (httpx.ConnectTimeout, "ai_before_send", False), (httpx.ReadTimeout, "ai_result_unknown", True),
    (httpx.WriteError, "ai_result_unknown", True),
])
def test_transport_distinguishes_pre_send_from_unknown(qwen, error, code, sent):
    def handle(request):
        raise error("Private upstream information", request=request)
    with pytest.raises(ProviderError, match=code) as failure:
        run(qwen, handle)
    assert failure.value.sent == sent


def test_missing_key_never_sends(qwen):
    qwen.ai_api_key = None
    with pytest.raises(ProviderError, match="ai_unavailable"):
        run(qwen, lambda _: pytest.fail("Unexpected outbound request"))


def test_mutated_settings_are_rechecked_before_constructing_a_request(qwen):
    qwen.ai_base_url = "https://unexpected.example.test/compatible-mode/v1"
    with pytest.raises(ProviderError, match="ai_configuration_changed") as failure:
        run(qwen, lambda _: pytest.fail("Untrusted destination reached the transport"))
    assert not failure.value.sent


def test_fake_is_rejected_in_production():
    with pytest.raises(ValidationError, match="prohibits the fake AI provider"):
        Settings(_env_file=None, jwt_secret=token_urlsafe(48), app_env="production",
                 app_origins=["https://food.example.test"], ai_enabled=True, ai_provider="fake")


def test_prepared_image_contains_pixels_without_metadata(tmp_path):
    source = tmp_path / "photo.webp"
    with Image.new("RGBA", (1800, 1200), (80, 40, 10, 0)) as image:
        exif = image.getexif()
        exif[271] = "fixture camera owner"
        image.save(source, "WEBP", exif=exif.tobytes())
    with Image.open(BytesIO(prepare_photo(source, 1024))) as jpeg:
        assert jpeg.size == (1024, 683) and jpeg.format == "JPEG" and not jpeg.getexif()
        assert jpeg.getpixel((0, 0)) == (255, 255, 255)
