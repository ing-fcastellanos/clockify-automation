from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _maybe_load_dotenv() -> None:
    if os.environ.get("CI"):
        return
    candidate = Path.cwd() / ".env"
    if candidate.is_file():
        load_dotenv(candidate)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        case_sensitive=True,
        extra="ignore",
    )

    jira_base_url: str = Field(alias="JIRA_BASE_URL", min_length=1)
    jira_email: str = Field(alias="JIRA_EMAIL", min_length=1)
    jira_api_token: str = Field(alias="JIRA_API_TOKEN", min_length=1)

    clockify_api_key: str = Field(alias="CLOCKIFY_API_KEY", min_length=1)
    clockify_workspace_id: str = Field(alias="CLOCKIFY_WORKSPACE_ID", min_length=1)
    clockify_project_id: str = Field(alias="CLOCKIFY_PROJECT_ID", min_length=1)
    clockify_tag_id: str = Field(alias="CLOCKIFY_TAG_ID", min_length=1)
    clockify_user_id: str | None = Field(default=None, alias="CLOCKIFY_USER_ID")

    timezone_name: str = Field(default="America/Mexico_City", alias="TIMEZONE")

    @field_validator("clockify_user_id", mode="before")
    @classmethod
    def _empty_string_is_none(cls, v: object) -> object:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("timezone_name")
    @classmethod
    def _validate_tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {v!r}") from exc
        return v

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)


def load_settings() -> Settings:
    _maybe_load_dotenv()
    return Settings()  # type: ignore[call-arg]


def load_holidays(path: Path | str = "holidays.yaml") -> frozenset[date]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"holidays file not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        return frozenset()
    if not isinstance(raw, list):
        raise ValueError(f"{p}: expected a YAML list of dates, got {type(raw).__name__}")

    parsed: set[date] = set()
    for i, item in enumerate(raw):
        if isinstance(item, date):
            parsed.add(item)
        elif isinstance(item, str):
            try:
                parsed.add(date.fromisoformat(item))
            except ValueError as exc:
                raise ValueError(f"{p}: item {i} is not a valid ISO date: {item!r}") from exc
        else:
            raise ValueError(
                f"{p}: item {i} must be a date or ISO string, got {type(item).__name__}"
            )
    return frozenset(parsed)
