"""本地假的 OpenAI 兼容服务，用于离线验证 AI 智能命题链路。

它只在测试中使用，不属于生产代码；生产代码里的提供商 URL、模型名称和密钥
全部来自用户配置（R2）。

启动：
    python -m tests.fake_llm_server 8899
"""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------------------
# 各阶段返回的固定内容（由系统提示中的 [STAGE:x] 标记区分）
# ---------------------------------------------------------------------------
ANALYZE = {
    "knowledge_points": ["循环", "输入输出", "整数求和"],
    "difficulty": "入门",
    "core_algorithm": "一次遍历累加",
    "io_style": "标准输入输出",
    "data_scale": "1 <= n <= 10^5，|a_i| <= 10^9",
    "edge_cases": ["n = 1", "全部为负数", "数据规模达到上限"],
    "test_dimensions": ["随机", "极端", "退化"],
}

STATEMENT = {
    "id": "ai_sum_array",
    "title": "数组求和",
    "description": "给定 n 个整数，求它们的和。",
    "input_description": "第一行一个整数 n（1 <= n <= 10^5），第二行 n 个整数，以空格分隔。",
    "output_description": "一行，输出这 n 个整数的和。",
    "samples": [{"input": "3\n1 2 3\n", "output": "6\n"}],
    "constraints": "1 <= n <= 10^5，|a_i| <= 10^9",
    "hint": "注意使用 64 位整数。",
    "source": "AI 智能命题",
    "tags": ["基础题", "模拟"],
    "time_limit": 1.0,
    "memory_limit": 128,
    "author": "AI",
    "difficulty": "入门",
}

REFERENCE_CODE = (
    "import sys\n"
    "data = sys.stdin.read().split()\n"
    "n = int(data[0])\n"
    "print(sum(int(x) for x in data[1:1 + n]))\n"
)

BRUTE_CODE = (
    "import sys\n"
    "data = sys.stdin.read().split()\n"
    "n = int(data[0])\n"
    "total = 0\n"
    "for i in range(n):\n"
    "    total += int(data[1 + i])\n"
    "print(total)\n"
)

GENERATOR_CODE = '''
import json, random
cases = []
for n in (1, 2, 5):
    values = [random.randint(-100, 100) for _ in range(n)]
    cases.append({"input": f"{n}\\n" + " ".join(map(str, values)) + "\\n",
                  "scale": "small", "note": f"小规模随机 n={n}"})
n = 1000
values = [10 ** 9] * n
cases.append({"input": f"{n}\\n" + " ".join(map(str, values)) + "\\n",
              "scale": "large", "note": "大规模上限数据"})
n = 100
values = [-10 ** 9] * n
cases.append({"input": f"{n}\\n" + " ".join(map(str, values)) + "\\n",
              "scale": "large", "note": "全负数边界"})
print(json.dumps(cases, ensure_ascii=False))
'''


def stage_payload(stage: str) -> dict:
    if stage == "analyze":
        return ANALYZE
    if stage == "statement":
        return STATEMENT
    if stage == "solution":
        return {"reference_code": REFERENCE_CODE, "brute_code": BRUTE_CODE,
                "explanation": "直接求和"}
    if stage == "generator":
        return {"generator_code": GENERATOR_CODE,
                "case_plan": ["小规模随机", "大规模上限", "全负数"]}
    return {"note": "unknown stage"}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError:
            payload = {}

        system = ""
        user_text = ""
        for message in payload.get("messages", []):
            if message.get("role") == "system":
                system = message.get("content", "")
            elif message.get("role") == "user":
                user_text += message.get("content", "")
        stage = "analyze"
        for name in ("analyze", "statement", "solution", "generator"):
            if f"[STAGE:{name}]" in system:
                stage = name
                break

        # 用于测试「中断」功能：包含关键字时故意拖慢响应
        if "慢速测试" in user_text:
            import time as _time

            _time.sleep(float(os.environ.get("FAKE_LLM_DELAY", "8")))

        content = json.dumps(stage_payload(stage), ensure_ascii=False)
        usage = {"prompt_tokens": 300, "completion_tokens": 200, "total_tokens": 500}

        if payload.get("stream"):
            self._stream(content, usage)
        else:
            self._json(content, usage)

    def _json(self, content: str, usage: dict) -> None:
        body = json.dumps({
            "id": "chatcmpl-fake", "object": "chat.completion", "model": "fake-model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                         "finish_reason": "stop"}],
            "usage": usage,
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream(self, content: str, usage: dict) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        step = 24
        for i in range(0, len(content), step):
            chunk = {"choices": [{"index": 0, "delta": {"content": content[i:i + step]},
                                  "finish_reason": None}]}
            self._chunk(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n")
        self._chunk(f"data: {json.dumps({'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}], 'usage': usage})}\n\n")
        self._chunk("data: [DONE]\n\n")
        self._chunk("")

    def _chunk(self, text: str) -> None:
        data = text.encode()
        self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")


def start(port: int = 8899) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


if __name__ == "__main__":  # pragma: no cover
    import sys
    import time

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    srv = start(port)
    print(f"fake llm server listening on http://127.0.0.1:{port}/v1")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        srv.shutdown()
