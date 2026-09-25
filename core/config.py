from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str = Field(default="postgresql+asyncpg://bbd:bbd@postgres:5432/bbd", repr=False)
    redis_url: str = Field(default="redis://redis:6379/0", repr=False)
    data_dir: Path = Path("/data")
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
