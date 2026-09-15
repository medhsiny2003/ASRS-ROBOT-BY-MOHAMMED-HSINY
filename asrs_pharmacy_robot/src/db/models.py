from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Medicine:
    id: int | None
    name: str
    x: float
    y: float
    stock: int
    location_label: str | None = None
    category: str | None = None
    expiry_date: str | None = None
    is_active: bool = True

