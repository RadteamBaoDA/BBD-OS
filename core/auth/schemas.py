from pydantic import BaseModel, Field


class SetupRequest(BaseModel):
    password: str = Field(min_length=12, max_length=128)


class SetupStatus(BaseModel):
    setupRequired: bool


class SetupResponse(BaseModel):
    created: bool


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class AuthState(BaseModel):
    authenticated: bool = True
    csrfToken: str


class CsrfResponse(BaseModel):
    csrfToken: str
