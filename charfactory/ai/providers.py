"""Conversa com os provedores de modelo pela API HTTP de cada um (urllib, sem SDKs):
Anthropic (Messages API), OpenAI e compatíveis (Chat Completions: OpenRouter, Ollama, LM Studio…)
e Google Gemini (generateContent).

Cada provedor guarda o histórico no formato nativo dele, devolvendo as mensagens do modelo sem
mexer: blocos de raciocínio (thinking da Anthropic, thoughtSignature do Gemini) precisam voltar
intactos no pedido seguinte.
"""
from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .tools import Result, Tool

TIMEOUT = 600


class ProviderError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class Call:
    id: str
    name: str
    args: dict
    bad_args: str | None = None          # JSON inválido vindo do modelo: volta como erro


@dataclass
class Turn:
    text: str = ""
    calls: list[Call] = field(default_factory=list)
    stop: str = ""


def _request(url: str, headers: dict, body: dict | None = None, method: str | None = None) -> dict:
    """Pedido com novas tentativas nos erros passageiros (provedor sobrecarregado, limite de
    taxa, conexão caída), esperando o Retry-After quando o provedor manda."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    for attempt in range(RETRIES + 1):
        req = urllib.request.Request(url, data, method=method or ("POST" if data else "GET"),
                                     headers={"Content-Type": "application/json", **headers})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            hint = e.headers.get("Retry-After") if e.headers else None
            m = re.search(r'"retryDelay"\s*:\s*"([\d.]+)s"', raw)      # o Gemini manda no corpo
            hint = hint or (m[1] if m else None)
            if e.code in RETRY_STATUS and attempt < RETRIES and _seconds(hint) <= MAX_WAIT:
                _sleep(_wait(attempt, hint))
                continue
            try:
                err = json.loads(raw)
                err = err[0] if isinstance(err, list) and err else err
                msg = (err.get("error") or {}).get("message") if isinstance(err.get("error"), dict) else err.get("error")
                msg = msg or err.get("message") or raw
            except (ValueError, AttributeError):
                msg = raw or e.reason
            raise ProviderError(f"HTTP {e.code}: {msg}", e.code) from None
        except TimeoutError:
            raise ProviderError(f"{url.split('/')[2]}: no answer in {TIMEOUT} s") from None
        except (urllib.error.URLError, OSError) as e:
            if attempt < RETRIES:
                _sleep(_wait(attempt, None))
                continue
            raise ProviderError(f"{url.split('/')[2]}: {getattr(e, 'reason', e)}") from None
    raise AssertionError("unreachable")


RETRIES = 3
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}      # 529: Anthropic sobrecarregada
_sleep = time.sleep


MAX_WAIT = 60.0          # pedir para esperar mais que isso (cota do dia) não vale a nova tentativa


def _seconds(retry_after: str | None) -> float:
    try:
        return max(float(retry_after), 0.0) if retry_after is not None else 0.0
    except ValueError:
        return 0.0


def _wait(attempt: int, retry_after: str | None) -> float:
    if retry_after is not None and _seconds(retry_after) > 0:
        return min(_seconds(retry_after), MAX_WAIT)
    return (2, 5, 12, 30)[min(attempt, 3)]


class Provider:
    name = ""
    label = ""
    default_model = ""
    needs_key = True
    default_base = ""

    def __init__(self, api_key: str = "", model: str = "", base_url: str = ""):
        self.api_key = api_key
        self.model = model or self.default_model
        self.base_url = (base_url or self.default_base).rstrip("/")

    def add_user(self, msgs: list, text: str) -> None:
        msgs.append({"role": "user", "content": text})

    def step(self, msgs: list, system: str, tools: list[Tool]) -> Turn:
        raise NotImplementedError

    def add_results(self, msgs: list, results: list[tuple[Call, Result]]) -> None:
        raise NotImplementedError

    def list_models(self) -> list[str]:
        raise NotImplementedError


# ======================================================================= Anthropic

class Anthropic(Provider):
    name = "anthropic"
    label = "Anthropic (Claude)"
    default_model = "claude-opus-5-5"
    default_base = "https://api.anthropic.com/v1"
    # modelos que aceitam o fallback do servidor quando um classificador recusa o pedido
    FALLBACK_MODELS = ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")
    # raciocínio adaptativo e esforço: Opus 4.6+, Sonnet 4.6 e a família 5 (o Haiku 4.5 e os
    # anteriores recusam). O Opus 5.5 usa 'medium' se nada for pedido: editar golpes em várias
    # etapas rende mais em 'high'
    ADAPTIVE = re.compile(r"^claude-(opus-4-[6-9]|sonnet-4-6|(opus|sonnet|haiku|fable|mythos)-5)")
    EFFORT = "high"

    def _headers(self) -> dict:
        h = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        if self.model in self.FALLBACK_MODELS:
            h["anthropic-beta"] = "server-side-fallback-2026-07-01"
        return h

    def step(self, msgs, system, tools):
        # cache_control no topo: o prefixo (ferramentas, sistema e a conversa até aqui) é lido do
        # cache a cada etapa do loop em vez de cobrado inteiro de novo
        body = {"model": self.model, "max_tokens": 16000, "system": system, "messages": msgs,
                "tools": [{"name": t.name, "description": t.description, "input_schema": t.schema()}
                          for t in tools],
                "cache_control": {"type": "ephemeral"}}
        if self.ADAPTIVE.match(self.model):
            body["thinking"] = {"type": "adaptive"}
            body["output_config"] = {"effort": self.EFFORT}
        if self.model in self.FALLBACK_MODELS:
            body["fallbacks"] = "default"
        r = _request(f"{self.base_url}/messages", self._headers(), body)
        content = r.get("content") or []
        # depois de um fallback no meio da resposta, o que veio antes do último bloco 'fallback'
        # (raciocínio e chamadas do modelo que recusou) não volta no histórico
        last = max((i for i, b in enumerate(content) if b.get("type") == "fallback"), default=-1)
        content = [b for i, b in enumerate(content)
                   if i > last or b.get("type") not in ("thinking", "redacted_thinking", "tool_use")]
        turn = Turn(stop=r.get("stop_reason") or "")
        if turn.stop == "refusal":
            details = r.get("stop_details") or {}
            turn.text = "The model declined this request" + (
                f" ({details['category']})" if details.get("category") else "") + "."
            return turn                          # a resposta recusada não entra no histórico
        msgs.append({"role": "assistant", "content": content})
        turn.text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
        turn.calls = [Call(b["id"], b["name"], b.get("input") or {}) for b in content if b.get("type") == "tool_use"]
        return turn

    def add_results(self, msgs, results):
        blocks = []
        for call, res in results:
            parts = [{"type": "text", "text": res.text}]
            parts += [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                   "data": base64.b64encode(p).decode("ascii")}} for p in res.images]
            blocks.append({"type": "tool_result", "tool_use_id": call.id, "content": parts,
                           **({"is_error": True} if res.is_error else {})})
        msgs.append({"role": "user", "content": blocks})     # todos os resultados numa mensagem só

    def list_models(self):
        r = _request(f"{self.base_url}/models?limit=100", self._headers())
        return [m["id"] for m in r.get("data", [])]


# ======================================================================= OpenAI e compatíveis

class OpenAI(Provider):
    name = "openai"
    label = "OpenAI (GPT)"
    default_model = "gpt-5"
    default_base = "https://api.openai.com/v1"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def step(self, msgs, system, tools):
        body = {"model": self.model, "messages": [{"role": "system", "content": system}, *msgs],
                "tools": [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                            "parameters": t.schema()}} for t in tools]}
        r = _request(f"{self.base_url}/chat/completions", self._headers(), body)
        choices = r.get("choices") or []
        if not choices:
            raise ProviderError(f"empty response: {json.dumps(r)[:300]}")
        m, stop = choices[0].get("message") or {}, choices[0].get("finish_reason") or ""
        calls = m.get("tool_calls") or []
        msg = {"role": "assistant", "content": m.get("content") or (None if calls else "")}
        if calls:
            msg["tool_calls"] = calls
        msgs.append(msg)
        turn = Turn(text=m.get("content") or m.get("refusal") or "", stop=stop)
        for c in calls:
            fn = c.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
                turn.calls.append(Call(c.get("id", ""), fn.get("name", ""), args if isinstance(args, dict) else {}))
            except ValueError:
                turn.calls.append(Call(c.get("id", ""), fn.get("name", ""), {}, fn.get("arguments")))
        return turn

    def add_results(self, msgs, results):
        images = []
        for call, res in results:
            text = ("ERROR: " if res.is_error else "") + res.text
            msgs.append({"role": "tool", "tool_call_id": call.id, "content": text})
            images += res.images
        if images:          # mensagem de ferramenta só leva texto: as imagens vão numa do usuário
            msgs.append({"role": "user", "content": [
                {"type": "text", "text": "Images returned by the tool calls above:"},
                *[{"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(p).decode("ascii")}}
                  for p in images]]})

    def list_models(self):
        r = _request(f"{self.base_url}/models", self._headers())
        return sorted(m["id"] for m in r.get("data", []))


class Compatible(OpenAI):
    name = "compatible"
    label = "OpenAI-compatible (OpenRouter, Ollama, LM Studio…)"
    default_model = ""
    default_base = "http://localhost:11434/v1"          # Ollama
    needs_key = False


# ======================================================================= Gemini

_GEMINI_DROP = {"additionalProperties", "default", "$schema", "examples"}


def _gemini_schema(s):
    """O Gemini aceita um subconjunto do JSON Schema (OpenAPI): tira o que ele recusa."""
    if isinstance(s, dict):
        return {k: _gemini_schema(v) for k, v in s.items() if k not in _GEMINI_DROP}
    if isinstance(s, list):
        return [_gemini_schema(v) for v in s]
    return s


class Gemini(Provider):
    name = "gemini"
    label = "Google Gemini"
    default_model = "gemini-flash-latest"         # apelido: sempre o Flash mais novo
    default_base = "https://generativelanguage.googleapis.com/v1beta"

    def _headers(self) -> dict:
        return {"x-goog-api-key": self.api_key}

    def add_user(self, msgs, text):
        msgs.append({"role": "user", "parts": [{"text": text}]})

    def step(self, msgs, system, tools):
        decls = []
        for t in tools:
            d = {"name": t.name, "description": t.description}
            if t.params:
                d["parameters"] = _gemini_schema(t.schema())
            decls.append(d)
        body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": msgs,
                "tools": [{"functionDeclarations": decls}]}
        model = self.model if self.model.startswith("models/") else f"models/{self.model}"
        r = _request(f"{self.base_url}/{model}:generateContent", self._headers(), body)
        cands = r.get("candidates") or []
        if not cands:
            block = (r.get("promptFeedback") or {}).get("blockReason")
            raise ProviderError(f"no answer from the model{f' (blocked: {block})' if block else ''}")
        content = cands[0].get("content") or {"role": "model", "parts": []}
        content.setdefault("role", "model")
        content.setdefault("parts", [])
        msgs.append(content)                         # partes intactas (thoughtSignature volta junto)
        turn = Turn(stop=cands[0].get("finishReason") or "")
        turn.text = "".join(p.get("text", "") for p in content["parts"] if not p.get("thought"))
        for i, p in enumerate(content["parts"]):
            fc = p.get("functionCall")
            if fc:
                turn.calls.append(Call(fc.get("id") or f"call_{len(msgs)}_{i}", fc.get("name", ""), fc.get("args") or {}))
        return turn

    def add_results(self, msgs, results):
        parts = []
        for call, res in results:
            fr = {"name": call.name, "response": {"error": res.text} if res.is_error else {"result": res.text}}
            if not call.id.startswith("call_"):
                fr["id"] = call.id
            parts.append({"functionResponse": fr})
            parts += [{"inlineData": {"mimeType": "image/png", "data": base64.b64encode(p).decode("ascii")}}
                      for p in res.images]
        msgs.append({"role": "user", "parts": parts})

    def list_models(self):
        r = _request(f"{self.base_url}/models?pageSize=200", self._headers())
        return sorted(m["name"].removeprefix("models/") for m in r.get("models", [])
                      if "generateContent" in m.get("supportedGenerationMethods", []))


PROVIDERS: dict[str, type[Provider]] = {p.name: p for p in (Anthropic, OpenAI, Gemini, Compatible)}


def make(name: str, api_key: str = "", model: str = "", base_url: str = "") -> Provider:
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ProviderError(f"unknown provider: {name}")
    return cls(api_key, model, base_url)
