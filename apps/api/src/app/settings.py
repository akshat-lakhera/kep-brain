"""Process settings, read from unprefixed environment variables (06 §4 C4).

A variable that is defined but empty counts as unset, so `.env.example`
can list every name without forcing a value.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SIG_SCOPE_DEFAULT = "sig-node,sig-scheduling,sig-apps"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"
    service_name: str = "kep-brain-api"
    public_base_url: str = "http://localhost:3000"

    falkordb_host: str = "localhost"
    falkordb_port: int = 6380
    falkordb_password: SecretStr | None = None
    falkordb_timeout_seconds: float = 5.0
    falkordb_acl_mode: Literal["aclfile", "single"] = "single"
    falkordb_reader_password: SecretStr | None = None
    falkordb_memory_password: SecretStr | None = None
    falkordb_ops_password: SecretStr | None = None
    falkordb_writer_password: SecretStr | None = None
    falkordb_image: str = "falkordb/falkordb:v4.22.0"

    enhancements_pin_sha: str = "8659e382efab7340d70de52432ee8f3d9979b797"
    community_pin_sha: str | None = None
    repo_cache_dir: str = "./repo_cache"
    sigs: str = SIG_SCOPE_DEFAULT
    sync_mode: Literal["pinned", "live"] = "pinned"
    tickets_as_of: str | None = None
    github_token: SecretStr | None = None

    llm_provider: Literal["anthropic", "openai_compatible"] = "openai_compatible"
    llm_model: str = "gemini-2.5-flash"
    llm_model_cheap: str = "gemini-2.5-flash-lite"
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_daily_budget_usd: float = 5.0
    llm_timeout_seconds: float = 60.0
    findings_agent_enabled: bool = True
    findings_agent_daily_usd: float = 1.0

    ask_rate_limit_per_10m: int = Field(default=30, ge=1)
    admin_token: SecretStr | None = None
    mcp_token: SecretStr | None = None
    mcp_port: int = 8765
    stale_after_hours: int = 24
    stale_tracker_gap_days: int = 90

    @field_validator("sigs")
    @classmethod
    def _sigs_non_empty(cls, value: str) -> str:
        items = [s.strip() for s in value.split(",") if s.strip()]
        if not items:
            raise ValueError("SIGS must name at least one SIG directory")
        return ",".join(items)

    @property
    def sig_list(self) -> list[str]:
        return self.sigs.split(",")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
