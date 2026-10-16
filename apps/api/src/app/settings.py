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
        # Repo-root .env first, then a local one (later files win).
        env_file=("../../.env", ".env"),
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"
    api_host: str = "0.0.0.0"
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

    # Public sources. Pins are optional overrides: unset means "latest default-branch head at sync start".
    enhancements_repo_url: str = "https://github.com/kubernetes/enhancements.git"
    community_repo_url: str = "https://github.com/kubernetes/community.git"
    # Holds the OWNERS files; read through the GitHub API, never cloned.
    owners_repo_url: str = "https://github.com/kubernetes/kubernetes.git"
    enhancements_pin_sha: str | None = None
    community_pin_sha: str | None = None
    owners_pin_sha: str | None = None
    git_timeout_seconds: int = Field(default=600, ge=10)
    repo_cache_dir: str = "./repo_cache"
    sigs: str = SIG_SCOPE_DEFAULT
    tickets_as_of: str | None = None
    github_token: SecretStr | None = None
    # Disk cache of GitHub GraphQL responses: auto = record in dev/test, off in prod. Delete the cache dir to refresh.
    github_cache: Literal["auto", "off", "record", "replay"] = "auto"

    llm_provider: Literal["anthropic", "openai_compatible"] = "openai_compatible"
    llm_model: str = "openai/gpt-oss-120b"
    llm_model_cheap: str = "openai/gpt-oss-20b"
    # Tried in order when the primary model answers 429/503.
    llm_fallback_models: str = "qwen/qwen3.8-27b"
    # Client-side pacing so a rate-limited provider (Groq free tier) is not hammered.
    llm_requests_per_minute: int = Field(default=25, ge=1)
    llm_max_retries: int = Field(default=4, ge=0)
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = "https://api.groq.com/openai/v1"
    llm_daily_budget_usd: float = 5.0
    llm_timeout_seconds: float = 60.0
    findings_agent_enabled: bool = True
    findings_agent_daily_usd: float = 1.0

    ask_rate_limit_per_10m: int = Field(default=30, ge=1)
    ask_daily_cap: int = Field(default=150, ge=1)
    trust_proxy: bool = False
    max_body_bytes: int = Field(default=65536, ge=1024)
    admin_token: SecretStr | None = None
    mcp_token: SecretStr | None = None
    mcp_port: int = 8765

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
    def llm_fallback_list(self) -> list[str]:
        return [m.strip() for m in self.llm_fallback_models.split(",") if m.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
