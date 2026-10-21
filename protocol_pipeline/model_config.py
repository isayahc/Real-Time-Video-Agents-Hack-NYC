"""Shared Nebius presets and model-specific direct-output request settings."""
from __future__ import annotations

import os
from typing import Any

DEFAULT_VISION_MODEL = "MiniMaxAI/MiniMax-M3"
DEFAULT_COMPILER_MODEL = "nvidia/Nemotron-3_5-Lightning"


def model_presets() -> dict[str, str]:
    """Resolve nonblank environment overrides without changing explicit choices."""
    return {
        "vision_model": os.getenv("NEBIUS_VISION_MODEL", "").strip() or DEFAULT_VISION_MODEL,
        "model": os.getenv("NEBIUS_COMPILER_MODEL", "").strip() or DEFAULT_COMPILER_MODEL,
    }


def generation_settings(model: str) -> dict[str, Any]:
    """Disable thinking only for exact models with documented template controls.

    Structured extraction needs visible JSON within its bounded output budget.
    Unknown/custom models retain their provider defaults; no generic thinking
    parameter or silent model substitution is applied.
    """
    if model == DEFAULT_COMPILER_MODEL:
        return {"chat_template_kwargs": {"enable_thinking": False}}
    if model == DEFAULT_VISION_MODEL:
        return {"chat_template_kwargs": {"thinking_mode": "disabled"}}
    return {}
