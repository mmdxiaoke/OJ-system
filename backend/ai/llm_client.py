"""OpenAI 兼容 Chat Completions 客户端。

* 支持普通请求与流式（SSE）请求，流式过程中回调增量文本用于实时进度；
* 统一收集 token 用量（含流式模式下的 usage 字段）；
* 异常信息中不包含 API Key。
"""
from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

DEFAULT_TIMEOUT = httpx.Timeout(connect=15.0, read=180.0, write=30.0, pool=15.0)
MAX_RETRIES = 2


@dataclass
class LLMResponse:
    content: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    usage_available: bool = False
    finish_reason: str = ""
    raw_meta: dict = field(default_factory=dict)


class LLMError(RuntimeError):
    """模型调用失败（消息中不含敏感信息）。"""


def chat_endpoint(provider_url: str) -> str:
    url = provider_url.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if re.search(r"/v\d+$", url) or re.search(r"/v\d+/", url):
        return f"{url}/chat/completions"
    return f"{url}/v1/chat/completions"


class LLMClient:
    def __init__(self, *, provider_url: str, model: str, api_key: str, timeout: httpx.Timeout | None = None) -> None:
        self.provider_url = provider_url
        self.model = model
        self._api_key = api_key
        self._timeout = timeout or DEFAULT_TIMEOUT

    @property
    def endpoint(self) -> str:
        return chat_endpoint(self.provider_url)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _payload(self, messages: list[dict], *, stream: bool, temperature: float, max_tokens: int | None) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if stream:
            # 让兼容 OpenAI 的服务端在流式响应末尾返回 usage
            payload["stream_options"] = {"include_usage": True}
        return payload

    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        """发起一次对话请求，自动重试可恢复错误。"""
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                return await self._chat_once(
                    messages, temperature=temperature, max_tokens=max_tokens, on_delta=on_delta
                )
            except LLMError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                raise LLMError(f"model service unreachable: {type(exc).__name__}") from None
        raise LLMError(f"model request failed: {type(last_error).__name__}")

    async def _chat_once(
        self,
        messages: list[dict],
        *,
        temperature: float,
        max_tokens: int | None,
        on_delta: Callable[[str], None] | None,
    ) -> LLMResponse:
        stream = on_delta is not None
        payload = self._payload(messages, stream=stream, temperature=temperature, max_tokens=max_tokens)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            if not stream:
                resp = await client.post(self.endpoint, headers=self._headers(), json=payload)
                self._raise_for_status(resp)
                return self._parse_full(resp.json())

            async with client.stream("POST", self.endpoint, headers=self._headers(), json=payload) as resp:
                if resp.status_code >= 400:
                    body = await resp.aread()
                    self._raise_for_status_text(resp.status_code, body)
                return await self._parse_stream(resp, on_delta)

    # ------------------------------------------------------------------
    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            self._raise_for_status_text(resp.status_code, resp.content)

    @staticmethod
    def _raise_for_status_text(status: int, body: bytes) -> None:
        message = ""
        try:
            data = json.loads(body.decode("utf-8", "replace"))
            err = data.get("error")
            if isinstance(err, dict):
                message = str(err.get("message", ""))
            elif isinstance(err, str):
                message = err
            elif data.get("message"):
                message = str(data["message"])
        except Exception:
            message = body.decode("utf-8", "replace")[:200]
        message = message.replace("\n", " ")[:300]
        if status in (401, 403):
            raise LLMError(f"model service rejected the credentials (HTTP {status}): {message}")
        if status == 429:
            raise LLMError(f"model service rate limited (HTTP 429): {message}")
        raise LLMError(f"model service error (HTTP {status}): {message}")

    @staticmethod
    def _parse_full(data: dict) -> LLMResponse:
        try:
            choice = data["choices"][0]
            content = (choice.get("message") or {}).get("content") or ""
            finish_reason = choice.get("finish_reason") or ""
        except (KeyError, IndexError, TypeError):
            raise LLMError("unexpected response structure from model service") from None
        usage = data.get("usage") or {}
        return LLMResponse(
            content=content,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
            usage_available=bool(usage),
            finish_reason=finish_reason,
            raw_meta={"model": data.get("model", "")},
        )

    async def _parse_stream(self, resp: httpx.Response, on_delta: Callable[[str], None]) -> LLMResponse:
        content_parts: list[str] = []
        usage: dict = {}
        finish_reason = ""
        async for line in resp.aiter_lines():
            if not line:
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if line == "[DONE]":
                break
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue
            if chunk.get("usage"):
                usage = chunk["usage"]
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                piece = delta.get("content")
                if piece:
                    content_parts.append(piece)
                    on_delta(piece)
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
        return LLMResponse(
            content="".join(content_parts),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
            usage_available=bool(usage),
            finish_reason=finish_reason,
        )


def extract_json(text: str) -> dict:
    """从模型输出中提取第一个 JSON 对象（容忍 ```json 代码块与前后说明文字）。"""
    if not text:
        raise LLMError("model returned an empty response")
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    if start == -1:
        raise LLMError("model response does not contain a JSON object")
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError as exc:
                    raise LLMError(f"invalid JSON in model response: {exc.msg}") from None
    raise LLMError("unterminated JSON object in model response")
