"""Type definitions for UI Entity Mapper."""
from __future__ import annotations

from typing import TypedDict


class TransformConfig(TypedDict, total=False):
    """Optional transform parameters for a mapping."""

    threshold: float
    input_min: float
    input_max: float
    output_min: float
    output_max: float
    invert: bool
    round: bool
    mirror_brightness: bool
    mirror_color_temp: bool


class MappingConfig(TypedDict):
    """Full configuration for a single mapping."""

    id: str
    name: str
    enabled: bool
    direction: str
    source_entity: str
    target_entity: str
    mode: str
    retry_delay_seconds: float
    max_retries: int
    prevent_loop: bool
    debounce_ms: int
    throttle_ms: int
    transform: TransformConfig