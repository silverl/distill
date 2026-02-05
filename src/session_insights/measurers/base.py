"""Base measurer interface and KPI result model."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class KPIResult(BaseModel):
    """JSON-serializable result of a KPI measurement."""

    kpi: str
    value: float = Field(ge=0.0, le=100.0)
    target: float = Field(ge=0.0, le=100.0)
    details: dict[str, object] = Field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.model_dump(), indent=2)


class Measurer(ABC):
    """Abstract base class for KPI measurers."""

    @abstractmethod
    def measure(self) -> KPIResult:
        """Run the measurement and return a KPIResult."""
        ...
