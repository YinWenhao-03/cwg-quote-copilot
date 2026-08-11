from __future__ import annotations

import logging
from typing import Any

from .config import get_settings

logger = logging.getLogger(__name__)


def setup_telemetry(app: Any) -> None:
    settings = get_settings()
    if not settings.otel_exporter_otlp_endpoint:
        return
    try:
        from openinference.instrumentation import using_attributes
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from phoenix.otel import register

        register(
            project_name=settings.otel_project_name,
            endpoint=settings.otel_exporter_otlp_endpoint,
        )
        FastAPIInstrumentor.instrument_app(app)
        app.state.telemetry_attributes = using_attributes
    except ImportError:
        logger.warning("Telemetry endpoint configured, but full telemetry dependencies are absent")
