import json
import logging
import os

import httpx

log = logging.getLogger(__name__)

X_SEARCH_SCHEMA = {
    "name": "x_search",
    "description": (
        "Search recent X (Twitter) posts for a query. Returns up to `limit` posts with "
        "author handle, timestamp, and text. X content reflects opinion or claim — "
        "always attribute it (e.g. 'According to @user on X, ...'), never present it as fact."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "limit": {"type": "integer", "description": "Max posts (1-100).", "default": 10},
        },
        "required": ["query"],
    },
}


def x_search(query: str, limit: int = 10) -> str:
    token = os.environ.get("X_BEARER_TOKEN")
    if not token:
        return "Error: X_BEARER_TOKEN not set."
    try:
        r = httpx.get(
            "https://api.twitter.com/2/tweets/search/recent",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "query": query,
                "max_results": max(10, min(limit, 100)),
                "tweet.fields": "author_id,created_at",
                "expansions": "author_id",
                "user.fields": "username",
            },
            timeout=30.0,
        )
        r.raise_for_status()
        body = r.json()
        users = {u["id"]: u["username"] for u in body.get("includes", {}).get("users", [])}
        tweets = body.get("data", [])[:limit]
        out = [
            {
                "url": f"https://x.com/{users.get(t['author_id'], 'i')}/status/{t['id']}",
                "author": users.get(t["author_id"]),
                "created_at": t.get("created_at"),
                "text": t["text"],
            }
            for t in tweets
        ]
        return json.dumps(out, indent=2)
    except Exception as e:
        log.warning("x_search failed: %s", e)
        return f"Error: {e}"
