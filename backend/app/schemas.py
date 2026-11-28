from typing import Annotated
from datetime import datetime
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, field_validator

Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")]
Nickname = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
NewPassword = Annotated[str, StringConstraints(min_length=12, max_length=128)]
LoginPassword = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Timezone = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountCredentials(Input):
    username: Username

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.lower()


class Registration(AccountCredentials):
    password: NewPassword
    nickname: Nickname


def normalize_email(value: str) -> str:
    value = value.strip()
    local, separator, domain = value.partition("@")
    if (not separator or len(value) > 254 or len(local) > 64
            or not re.fullmatch(r"[A-Za-z0-9_+!#$%&'*=/^\x60{|}~?-]+(?:\.[A-Za-z0-9_+!#$%&'*=/^\x60{|}~?-]+)*", local)):
        raise ValueError("Invalid email address")
    domain = domain.lower()
    if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", domain):
        raise ValueError("Invalid email domain")
    return local + "@" + domain


class Login(Input):
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254)]
    password: LoginPassword

    @field_validator("username")
    @classmethod
    def normalize_identity(cls, value):
        if "@" in value:
            return normalize_email(value)
        if not re.fullmatch(r"[a-zA-Z0-9_]{3,32}", value):
            raise ValueError("Invalid username")
        return value.lower()


class ProfilePatch(Input):
    nickname: Nickname


class SettingsPatch(Input):
    timezone: Timezone | None = None
    show_calories: StrictBool | None = None
    show_nutrition: StrictBool | None = None

    @field_validator("timezone", "show_calories", "show_nutrition")
    @classmethod
    def valid_setting(cls, value, info):
        if value is None:
            raise ValueError("Settings may not be null")
        if info.field_name == "timezone":
            try:
                ZoneInfo(value)
            except (ValueError, ZoneInfoNotFoundError):
                raise ValueError("Use an IANA timezone name") from None
        return value


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: str
    username: str
    nickname: str
    avatar_key: str | None
    created_at: datetime
    updated_at: datetime


class UserPreferences(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timezone: str
    show_calories: bool
    show_nutrition: bool
    created_at: datetime
    updated_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfile


class SystemStatus(BaseModel):
    status: str = Field(examples=["ok"])
