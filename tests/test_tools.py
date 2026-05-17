import httpx
import respx

from shelfie import tools


def test_x_search_no_token(monkeypatch) -> None:
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    out = tools.x_search("anything")
    assert "X_BEARER_TOKEN" in out


@respx.mock
def test_x_search_ok(monkeypatch) -> None:
    monkeypatch.setenv("X_BEARER_TOKEN", "t")
    respx.get("https://api.twitter.com/2/tweets/search/recent").mock(
        return_value=httpx.Response(200, json={
            "data": [{"id": "1", "text": "hello", "author_id": "u1", "created_at": "2026-01-01"}],
            "includes": {"users": [{"id": "u1", "username": "alice"}]},
        })
    )
    out = tools.x_search("topic", limit=1)
    assert "alice" in out
    assert "hello" in out


@respx.mock
def test_x_search_http_error(monkeypatch) -> None:
    monkeypatch.setenv("X_BEARER_TOKEN", "t")
    respx.get("https://api.twitter.com/2/tweets/search/recent").mock(
        return_value=httpx.Response(500)
    )
    out = tools.x_search("topic")
    assert out.startswith("Error:")
