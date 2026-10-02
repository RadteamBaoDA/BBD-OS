from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.model_gateway.schemas import ModelMapping, PrivacySettings


class OwnerPreferencesRead(BaseModel):
    """Expose persisted theme, locale, timezone, and configuration revision state."""
    configuration_revision: int = Field(ge=1)
    persisted: bool = False
    theme: Literal["light", "dark", "system"]
    locale: Literal["en-us", "vi-vi"]
    timezone: str


class OwnerPreferencesUpdate(BaseModel):
    """Validate a revision-fenced owner preference update."""
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    theme: Literal["light", "dark", "system"]
    locale: Literal["en-us", "vi-vi"]
    timezone: str = Field(min_length=1, max_length=100)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Accept only timezone identifiers resolvable by the IANA zone database."""
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Timezone must be a valid IANA timezone") from exc
        return value

__all__ = ["ModelMapping", "PrivacySettings", "OwnerPreferencesRead", "OwnerPreferencesUpdate"]
