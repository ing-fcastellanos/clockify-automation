from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from clockify_automation.config import Settings, load_holidays

_REQUIRED_ENV = {
    "JIRA_BASE_URL": "https://example.atlassian.net",
    "JIRA_EMAIL": "user@example.com",
    "JIRA_API_TOKEN": "token-xyz",
    "CLOCKIFY_API_KEY": "ck-key",
    "CLOCKIFY_WORKSPACE_ID": "ws-1",
    "CLOCKIFY_PROJECT_ID": "proj-1",
    "CLOCKIFY_TAG_ID": "tag-1",
}


@pytest.fixture
def env_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in [
        *_REQUIRED_ENV,
        "CLOCKIFY_USER_ID",
        "TIMEZONE",
        "CI",
    ]:
        monkeypatch.delenv(k, raising=False)


def _set_required(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)


def test_missing_required_env_raises(env_clean: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_loads_with_required_env(env_clean: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    _set_required(monkeypatch)
    s = Settings()  # type: ignore[call-arg]
    assert s.jira_base_url == "https://example.atlassian.net"
    assert s.clockify_user_id is None
    assert s.timezone_name == "America/Mexico_City"
    assert str(s.timezone) == "America/Mexico_City"


def test_clockify_user_id_empty_string_treated_as_none(
    env_clean: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CI", "true")
    _set_required(monkeypatch)
    monkeypatch.setenv("CLOCKIFY_USER_ID", "")
    s = Settings()  # type: ignore[call-arg]
    assert s.clockify_user_id is None


def test_invalid_timezone_rejected(env_clean: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    _set_required(monkeypatch)
    monkeypatch.setenv("TIMEZONE", "Mars/Olympus_Mons")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_holidays_parses_iso_strings(tmp_path: Path) -> None:
    p = tmp_path / "holidays.yaml"
    p.write_text("- 2026-01-01\n- 2026-12-25\n", encoding="utf-8")
    holidays = load_holidays(p)
    assert holidays == frozenset({date(2026, 1, 1), date(2026, 12, 25)})


def test_holidays_accepts_native_yaml_dates(tmp_path: Path) -> None:
    # YAML can parse "2026-01-01" as a native date object too.
    p = tmp_path / "holidays.yaml"
    p.write_text("- 2026-01-01\n", encoding="utf-8")
    holidays = load_holidays(p)
    assert date(2026, 1, 1) in holidays


def test_holidays_empty_file_returns_empty_set(tmp_path: Path) -> None:
    p = tmp_path / "holidays.yaml"
    p.write_text("", encoding="utf-8")
    assert load_holidays(p) == frozenset()


def test_holidays_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_holidays(tmp_path / "missing.yaml")


def test_holidays_malformed_top_level_raises(tmp_path: Path) -> None:
    p = tmp_path / "holidays.yaml"
    p.write_text("not_a_list: true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expected a YAML list"):
        load_holidays(p)


def test_holidays_invalid_date_string_raises(tmp_path: Path) -> None:
    p = tmp_path / "holidays.yaml"
    p.write_text("- not-a-date\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not a valid ISO date"):
        load_holidays(p)
