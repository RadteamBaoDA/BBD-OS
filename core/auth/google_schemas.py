from pydantic import BaseModel, Field


class GoogleStartRequest(BaseModel):
    """Selects Google login or account linking flow."""
    purpose: str = Field(pattern="^(login|link)$")


class GoogleStatus(BaseModel):
    """Reports Google OAuth configuration and current link state."""
    configured: bool
    linked: bool


class GoogleStartResponse(BaseModel):
    """Returns the Google authorization URL for the initiated flow."""
    authorization_url: str


class ReauthenticateRequest(BaseModel):
    """Validated password request for recent-authentication confirmation."""
    password: str = Field(min_length=1, max_length=128)
