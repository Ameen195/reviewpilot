import hashlib
import json
import logging
from pathlib import Path

from groq import Groq

from reviewpilot.config import get_settings

log = logging.getLogger(__name__)
CACHE_DIR = Path("data/cache")
_client: Groq | None = None


def _groq() -> Groq:
    global _client
    if _client is None:
        # The SDK retries 429s with exponential backoff and honours Retry-After.
        _client = Groq(api_key=get_settings().groq_api_key, max_retries=6)
    return _client


def chat_json(model: str, system: str, user: str, client=None) -> tuple[dict, int]:
    """One JSON-mode call. Returns (parsed reply, tokens used; 0 on a cache hit)."""
    key = hashlib.sha256(json.dumps([model, system, user]).encode()).hexdigest()
    path = CACHE_DIR / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), 0
    r = (client or _groq()).chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        reasoning_effort="low",  # gpt-oss needs low effort + room for tokens or JSON mode fails
        max_tokens=2000,
        temperature=0,
    )
    data = json.loads(r.choices[0].message.content)
    tokens = r.usage.total_tokens
    log.info("groq %s tokens=%d", model, tokens)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data, tokens
