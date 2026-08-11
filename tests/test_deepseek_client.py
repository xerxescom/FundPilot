from types import SimpleNamespace

from app.services.ai import deepseek_client


def test_deepseek_client_uses_openai_compatible_chat_endpoint(monkeypatch):
    settings = SimpleNamespace(
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-v4-flash",
        deepseek_timeout=30.0,
        deepseek_api_key="test-key",
        online_llm_api_key="",
    )
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "结构化复盘"}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(deepseek_client, "get_settings", lambda: settings)
    monkeypatch.setattr(deepseek_client.httpx, "post", fake_post)

    content = deepseek_client.DeepSeekClient().generate("请复盘")

    assert content == "结构化复盘"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"]["model"] == "deepseek-v4-flash"
