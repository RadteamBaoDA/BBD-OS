from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str = Field(default="postgresql+asyncpg://bbd:bbd@postgres:5432/bbd", repr=False)
    redis_url: str = Field(default="redis://redis:6379/0", repr=False)
    data_dir: Path = Path("/data")
    upload_max_bytes: int = Field(default=25 * 1024 * 1024, gt=0, le=1024 * 1024 * 1024)
    parser_timeout_seconds: int = Field(default=120, gt=0, le=3600)
    docx_expanded_max_bytes: int = Field(default=100 * 1024 * 1024, gt=0)
    pdf_page_max: int = Field(default=500, gt=0)
    storage_orphan_grace_seconds: int = Field(default=3600, gt=0)
    browser_service_url: AnyHttpUrl = AnyHttpUrl("http://browser:8001")
    browser_shared_token: SecretStr = SecretStr("")
    n8n_service_url: AnyHttpUrl = Field(default=AnyHttpUrl("http://n8n:5678"), validation_alias="N8N_SERVICE_URL")
    n8n_source_id: str = Field(default="", validation_alias="BBD_SOURCE_ID")
    n8n_webhook_token: SecretStr = Field(default=SecretStr(""), validation_alias="N8N_WEBHOOK_TOKEN")
    public_origin: AnyHttpUrl = AnyHttpUrl("http://localhost:3000")
    secure_cookies: bool = False
    setup_token: SecretStr = SecretStr("")
    csrf_signing_secret: SecretStr = SecretStr("")
    session_lifetime_hours: int = Field(default=24, gt=0, le=720)
    omniroute_base_url: AnyHttpUrl | None = Field(default=None, repr=False)
    omniroute_api_key: SecretStr = SecretStr("")

    @field_validator("omniroute_base_url", mode="before")
    @classmethod
    def blank_gateway_url_is_unconfigured(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("public_origin")
    @classmethod
    def require_origin_only(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.path not in ("", "/") or value.query or value.fragment or value.username:
            raise ValueError("public_origin must contain only scheme and host")
        return value
