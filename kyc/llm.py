"""Minimal client for a local OpenAI-compatible server (no API key)."""
import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = os.environ.get("KYC_LLM_URL", "http://127.0.0.1:8093/v1/chat/completions")
OCR_MODEL = "surya-ocr"
LLM_MODEL = "gemma4-12b"
TIMEOUT = 900  # first call may load the model (2-4 min)


class LLMError(RuntimeError):
    pass


def image_part(path):
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}


def chat(model, messages, max_tokens=1500, no_think=True, timeout=TIMEOUT):
    body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
    if no_think:  # Gemma: disable thinking
        body["think"] = False
        body["chat_template_kwargs"] = {"enable_thinking": False}
    data = json.dumps(body).encode()
    last = None
    for attempt in (1, 2):  # retry once
        try:
            req = urllib.request.Request(URL, data, {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.load(r)
            return out["choices"][0]["message"]["content"] or ""
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} from model server: {e.read()[:300]!r}"
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            last = (f"Cannot reach model server at {URL} ({e}). "
                    "Is it running? Use --mock to run without it.")
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            last = f"Unexpected response from model server: {e}"
        if attempt == 1:
            time.sleep(2)
    raise LLMError(last)


def ocr_image(path):
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": "Extract all text from this image exactly as written."}, image_part(path)]}]
    return chat(OCR_MODEL, msgs, max_tokens=2000, no_think=False)


def parse_json_block(text):
    """Parse the first JSON object in a model reply (tolerates ```json fences and chatter)."""
    t = (text or "").strip()
    if "```" in t:
        parts = t.split("```")
        for p in parts[1::2]:
            p = p[4:] if p.lower().startswith("json") else p
            if "{" in p:
                t = p
                break
    i = t.find("{")
    if i < 0:
        raise ValueError("no JSON object in model reply")
    obj, _ = json.JSONDecoder().raw_decode(t[i:])
    if not isinstance(obj, dict):
        raise ValueError("JSON reply is not an object")
    return obj
