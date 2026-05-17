import json
import logging
import os

import httpx

log = logging.getLogger(__name__)

GROK_MODEL = "grok-4-fast"

X_SEARCH_SCHEMA = {
    "name": "x_search",
    "description": (
        "Search recent X (Twitter) posts about a query via xAI Grok Live Search. "
        "Returns a brief summary of what's being said on X plus citation URLs. "
        "X content reflects opinion or claim — always attribute it "
        "(e.g. 'According to posts on X, ...') and never present it as established fact."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "limit": {
                "type": "integer",
                "description": "Max X sources to consult (1-30).",
                "default": 15,
            },
        },
        "required": ["query"],
    },
}


def x_search(query: str, limit: int = 15) -> str:
    key = os.environ.get("XAI_API_KEY")
    if not key:
        return "Error: XAI_API_KEY not set."
    try:
        r = httpx.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": GROK_MODEL,
                "messages": [{
                    "role": "user",
                    "content": (
                        f"Summarize what people are currently saying on X about: {query}. "
                        "Quote handles when relevant and capture any disagreement."
                    ),
                }],
                "search_parameters": {
                    "mode": "on",
                    "sources": [{"type": "x"}],
                    "max_search_results": max(1, min(limit, 30)),
                    "return_citations": True,
                },
            },
            timeout=60.0,
        )
        r.raise_for_status()
        body = r.json()
        summary = body["choices"][0]["message"]["content"]
        citations = body.get("citations", [])
        return json.dumps({"summary": summary, "citations": citations}, indent=2)
    except Exception as e:
        log.warning("x_search failed: %s", e)
        return f"Error: {e}"
