"""M3 应用工厂：显式依赖注入装配 FastAPI（M3-02）。"""

from app.modules.application.app_factory.factory import (
    PortInUseError,
    create_app,
    ensure_port_available,
)
from app.modules.application.app_factory.health import (
    AnalysisHealthPort,
    HealthView,
)

__all__ = [
    "AnalysisHealthPort",
    "HealthView",
    "PortInUseError",
    "create_app",
    "ensure_port_available",
]
