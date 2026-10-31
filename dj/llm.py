"""LLM providers: llama.cpp (OpenAI-compatible, loopback) → Ollama → OpenAI. Stdlib only.

Pick explicitly with DJ_PROVIDER=llamacpp|ollama|openai, or leave unset for auto.
"""
import json
import os
import socket
import urllib.request
from urllib.parse import urlparse

LLAMACPP_URL = os.environ.get("DJ_LLAMACPP_URL", "http://127.0.0.1:8080")
LLAMACPP_MODEL = os.environ.get("DJ_LLAMACPP_MODEL", "local")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("DJ_OLLAMA_MODEL", "gemma4:e2b-it-qat")
OPENAI_BASE = "https://api.openai.com/v1"  # fixed host, never env-controlled
OPENAI_MODEL = os.environ.get("DJ_OPENAI_MODEL", "gpt-4o-mini")
TIMEOUT = int(os.environ.get("DJ_LLM_TIMEOUT", "300"))


def _assert_safe(url):
    """Allow https to api.openai.com, or plain http to a loopback host only.
    Loopback is by design: the DJ talks only to local servers or OpenAI —
    no user-controllable remote URLs ever enter a request."""
    u = urlparse(url)
    if u.scheme == "https" and u.hostname == "api.openai.com":
        return
    if u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1", "::1"):
        if u.hostname in ("127.0.0.1", "::1"):
            return  # literal loopback IPs — no resolution needed
        ip = socket.gethostbyname(u.hostname)  # pin resolution, block DNS rebinding
        if ip.startswith("127."):
            return
    raise ValueError(f"blocked unsafe URL: {url}")


def _post(url, payload, headers=None, timeout=TIMEOUT):
    _assert_safe(url)
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _llamacpp(messages):
    """llama-server exposes /v1/chat/completions (OpenAI-compatible)."""
    r = _post(f"{LLAMACPP_URL}/v1/chat/completions",
              {"model": LLAMACPP_MODEL, "messages": messages, "stream": False})
    return r["choices"][0]["message"]["content"]


def _ollama(messages):
    payload = {"model": OLLAMA_MODEL, "messages": messages,
               "stream": False, "think": False}
    try:
        r = _post(f"{OLLAMA_URL}/api/chat", payload)
    except Exception:
        payload.pop("think", None)  # older servers reject the key
        r = _post(f"{OLLAMA_URL}/api/chat", payload)
    return r["message"]["content"]


def _openai(messages):
    key = os.environ["OPENAI_API_KEY"]
    r = _post(f"{OPENAI_BASE}/chat/completions",
              {"model": OPENAI_MODEL, "messages": messages},
              headers={"Authorization": f"Bearer {key}"})
    return r["choices"][0]["message"]["content"]


def chat(messages):
    """Return assistant text. Explicit DJ_PROVIDER wins; auto tries
    llama.cpp, then Ollama, then OpenAI."""
    provider = os.environ.get("DJ_PROVIDER", "auto")
    if provider == "llamacpp":
        return _llamacpp(messages)
    if provider == "ollama":
        return _ollama(messages)
    if provider == "openai":
        return _openai(messages)

    errors = []
    for fn in (_llamacpp, _ollama):
        try:
            return fn(messages)
        except Exception as e:
            errors.append(f"{fn.__name__[1:]}: {e}")
    if os.environ.get("OPENAI_API_KEY"):
        return _openai(messages)
    raise RuntimeError(
        "No AI available. Tried: " + " | ".join(errors) +
        ". Start llama-server (:8080) or `ollama serve`, or export OPENAI_API_KEY.")
