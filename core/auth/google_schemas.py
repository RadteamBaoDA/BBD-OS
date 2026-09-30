from pydantic import BaseModel, Field


class GoogleStartRequest(BaseModel):
    purpose: str = Field(pattern="^(login|link)$")


class GoogleStatus(BaseModel):
    configured: bool
    linked: bool


class GoogleStartResponse(BaseModel):
    authorization_url: str


class ReauthenticateRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)
