"""Environment-driven configuration. Local defaults; constructed on demand, never at import."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    """Raised when a MANUS_* env var has an unparseable value."""


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _env_path(name: str, default: str) -> Path:
    return Path(_env_str(name, default)).expanduser()


@dataclass(frozen=True)
class Config:
    """All knobs of the agent. Defaults describe a fully local setup."""

    base_url: str = "http://127.0.0.1:11434/v1"
    api_key: str = "ollama"
    model: str = "qwen3:4b"
    max_steps: int = 30
    step_max_tokens: int = 512
    shell_timeout_s: int = 60
    net_timeout_s: int = 30
    observe_cap_bytes: int = 10_240
    search_cap_results: int = 5
    workspace: Path = field(default_factory=lambda: Path("~/manus_workspace").expanduser())
    reasoning_effort: str = "none"
    db_path: Path = field(
        default_factory=lambda: Path("~/.local/share/diy-manus/sessions.db").expanduser()
    )
    search_backend: str = "ddgs"
    searxng_url: str = ""

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            base_url=_env_str("MANUS_BASE_URL", "http://127.0.0.1:11434/v1"),
            api_key=_env_str("MANUS_API_KEY", "ollama"),
            model=_env_str("MANUS_MODEL", "qwen3:4b"),
            max_steps=_env_int("MANUS_MAX_STEPS", 30),
            step_max_tokens=_env_int("MANUS_STEP_MAX_TOKENS", 512),
            shell_timeout_s=_env_int("MANUS_SHELL_TIMEOUT_S", 60),
            net_timeout_s=_env_int("MANUS_NET_TIMEOUT_S", 30),
            observe_cap_bytes=_env_int("MANUS_OBSERVE_CAP_BYTES", 10_240),
            search_cap_results=_env_int("MANUS_SEARCH_CAP_RESULTS", 5),
            workspace=_env_path("MANUS_WORKSPACE", "~/manus_workspace"),
            reasoning_effort=_env_str("MANUS_REASONING_EFFORT", "none"),
            db_path=_env_path("MANUS_DB", "~/.local/share/diy-manus/sessions.db"),
            search_backend=_env_str("MANUS_SEARCH_BACKEND", "ddgs"),
            searxng_url=_env_str("MANUS_SEARXNG_URL", ""),
        )
