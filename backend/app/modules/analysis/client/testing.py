"""同合同测试客户端（M2-03，规格第 15.1 节确定性验收用）。

ScriptedGlmClient 与 GlmClient 满足同一 AnalysisModelClient 协议：
按脚本顺序返回预设响应、原样抛出预设 GlmClientError，并记录全部收到的请求。
只供测试注入使用，不进入生产运行链。
"""

from __future__ import annotations

from collections.abc import Iterable

from app.modules.analysis.client.errors import GlmClientError
from app.modules.analysis.client.models import GlmRequest, GlmResponse

__all__ = ["ScriptedGlmClient"]


class ScriptedGlmClient:
    """按脚本逐项响应的测试客户端；脚本耗尽时快速失败。"""

    def __init__(self, outcomes: Iterable[GlmResponse | GlmClientError] = ()) -> None:
        self._outcomes: list[GlmResponse | GlmClientError] = list(outcomes)
        self.requests: list[GlmRequest] = []

    def complete(self, request: GlmRequest) -> GlmResponse:
        self.requests.append(request)
        if not self._outcomes:
            raise AssertionError("脚本已耗尽：测试客户端收到的调用多于预设结果")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, GlmClientError):
            raise outcome
        return outcome
