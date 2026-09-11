"""应用工厂：HealthView 与分析健康探针端口（技术实施规格 12.2、第 14 节）。"""

from typing import Protocol

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from app.modules.application.config.settings import Settings


class HealthView(BaseModel):
    """GET /api/v1/health 的唯一响应结构（规格 12.2 字段白名单）。

    业务 DTO 不返回密钥内容、供应商原始响应或本机绝对路径。
    """

    model_config = ConfigDict(extra="forbid")

    app_status: str
    database_status: str
    analysis_status: str
    message: str


class AnalysisHealthPort(Protocol):
    """M2 分析服务的最小健康探针端口。

    真实分析端口合同由 M2-01/M3-05 冻结；本端口只服务 HealthView 的
    analysis_status 判定。生产装配不传入任何 Fake——Fake 只存在于
    测试边界（规格第 6 节），缺密钥时 HealthView 明确显示分析不可用。
    """

    def health_check(self) -> bool: ...


def register_health(app: FastAPI) -> None:
    @app.get("/api/v1/health", response_model=HealthView)
    def read_health() -> HealthView:
        settings: Settings = app.state.settings
        gateway: AnalysisHealthPort | None = getattr(app.state, "analysis_health", None)
        if gateway is not None:
            available = gateway.health_check()
            message_reader = getattr(gateway, "health_message", None)
            default_message = (
                "分析服务健康检查通过" if available else "分析服务健康检查失败"
            )
            custom_message = message_reader() if callable(message_reader) else None
            message = custom_message if isinstance(custom_message, str) else default_message
        elif settings.zai_api_key is not None:
            available = False
            message = "已配置 ZAI_API_KEY，但真实分析引擎尚未装配"
        else:
            available = False
            message = "未配置 ZAI_API_KEY，分析不可用；历史结果仍可查看"
        return HealthView(
            app_status="READY",
            database_status="READY",
            analysis_status="AVAILABLE" if available else "UNAVAILABLE",
            message=message,
        )
