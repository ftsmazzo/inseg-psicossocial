import json
import os
import urllib.request
from pathlib import Path

# load .env manually for CLI test
env_path = Path(__file__).resolve().parents[1] / "backend" / ".env"
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip())

key = os.environ.get("OPENROUTER_API_KEY", "")
model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
if model and "/" not in model:
    model = f"openai/{model}"

print("key_set", bool(key), "len", len(key))
print("model", model)

payload = {
    "model": model,
    "temperature": 0,
    "messages": [
        {"role": "user", "content": 'Responda JSON: {"ok": true}'},
    ],
    "response_format": {"type": "json_object"},
}
req = urllib.request.Request(
    "https://openrouter.ai/api/v1/chat/completions",
    data=json.dumps(payload).encode("utf-8"),
    method="POST",
    headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://inseg.local",
        "X-OpenRouter-Title": "Inseg Psicossocial",
    },
)
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    print("status ok")
    print("content", body["choices"][0]["message"]["content"][:200])
except Exception as e:
    if hasattr(e, "read"):
        print("http_error", e.read().decode("utf-8", errors="replace")[:500])
    else:
        print("error", e)
