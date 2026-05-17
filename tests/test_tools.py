import json

import httpx
import respx

from shelfie import tools


def test_x_search_no_key(monkeypatch) -> None:
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    out = tools.x_search("anything")
    assert "XAI_API_KEY" in out


@respx.mock
def test_x_search_ok(monkeypatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "k")
    route = respx.post("https://api.x.ai/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": "People on X say it's interesting."}}],
            "citations": ["https://x.com/alice/status/1", "https://x.com/bob/status/2"],
        })
    )
    out = tools.x_search("topic", limit=5)
    data = json.loads(out)
    assert "interesting" in data["summary"]
    assert len(data["citations"]) == 2
    sent = json.loads(route.calls[0].request.content)
    assert sent["search_parameters"]["sources"] == [{"type": "x"}]
    assert sent["search_parameters"]["max_search_results"] == 5
    assert sent["model"] == tools.GROK_MODEL


@respx.mock
def test_x_search_clamps_limit(monkeypatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "k")
    route = respx.post("https://api.x.ai/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": ""}}], "citations": [],
        })
    )
    tools.x_search("topic", limit=999)
    sent = json.loads(route.calls[0].request.content)
    assert sent["search_parameters"]["max_search_results"] == 30


@respx.mock
def test_x_search_http_error(monkeypatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "k")
    respx.post("https://api.x.ai/v1/chat/completions").mock(
        return_value=httpx.Response(500)
    )
    out = tools.x_search("topic")
    assert out.startswith("Error:")
