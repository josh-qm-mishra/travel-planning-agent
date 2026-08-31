"""Tests for configuration loading behavior.

No real credentials are read. Tests use temporary .env files or
patch.dict(os.environ) to exercise the precedence rules without
touching the actual repository-root .env.
"""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import Settings, _ENV_FILE


# ---------------------------------------------------------------------------
# .env path resolution
# ---------------------------------------------------------------------------


def test_env_file_path_is_absolute():
    assert _ENV_FILE.is_absolute()


def test_env_file_named_dotenv():
    assert _ENV_FILE.name == ".env"


def test_env_file_resolves_to_repo_root():
    """_ENV_FILE's parent must contain a 'backend/' sibling, confirming repo root."""
    assert (_ENV_FILE.parent / "backend").is_dir()


def test_env_file_registered_in_model_config():
    assert Settings.model_config.get("env_file") == str(_ENV_FILE)


def test_env_prefix_preserved():
    assert Settings.model_config.get("env_prefix") == "APP_"


# ---------------------------------------------------------------------------
# Precedence: OS env vars beat .env file values
# ---------------------------------------------------------------------------


def test_os_env_var_beats_env_file(tmp_path):
    """An OS environment variable shadows the same key in a .env file."""
    fake_env = tmp_path / ".env"
    fake_env.write_text("GOOGLE_API_KEY=from-file\n", encoding="utf-8")

    with patch.dict(os.environ, {"GOOGLE_API_KEY": "from-os-env"}, clear=False):
        s = Settings(_env_file=str(fake_env))

    assert s.google_api_key == "from-os-env"


def test_prefixed_os_env_var_beats_env_file(tmp_path):
    """APP_-prefixed OS env var overrides the same prefixed key in a .env file."""
    fake_env = tmp_path / ".env"
    # Use the same APP_-prefixed key in the file so pydantic-settings resolves both
    # values through the same alias, making precedence unambiguous.
    fake_env.write_text("APP_OPENAI_MODEL=model-from-file\n", encoding="utf-8")

    with patch.dict(os.environ, {"APP_OPENAI_MODEL": "model-from-os"}, clear=False):
        s = Settings(_env_file=str(fake_env))

    assert s.openai_model == "model-from-os"


# ---------------------------------------------------------------------------
# .env file values are loaded when no OS env var is set
# ---------------------------------------------------------------------------


def test_env_file_value_loaded_when_no_os_var(tmp_path):
    """A value present only in the .env file is picked up."""
    fake_env = tmp_path / ".env"
    fake_env.write_text("OPENAI_MODEL=gpt-from-file\n", encoding="utf-8")

    scrubbed = {
        k: v for k, v in os.environ.items()
        if k not in ("OPENAI_MODEL", "APP_OPENAI_MODEL")
    }
    with patch.dict(os.environ, scrubbed, clear=True):
        s = Settings(_env_file=str(fake_env))

    assert s.openai_model == "gpt-from-file"


def test_env_file_multiple_keys(tmp_path):
    """Multiple keys in a .env file are all loaded."""
    fake_env = tmp_path / ".env"
    fake_env.write_text(
        "GOOGLE_API_KEY=gkey\nOPENAI_API_KEY=okey\nOPENAI_MODEL=gpt-x\n",
        encoding="utf-8",
    )

    scrubbed = {
        k: v for k, v in os.environ.items()
        if k not in (
            "GOOGLE_API_KEY", "APP_GOOGLE_API_KEY",
            "OPENAI_API_KEY", "APP_OPENAI_API_KEY",
            "OPENAI_MODEL", "APP_OPENAI_MODEL",
        )
    }
    with patch.dict(os.environ, scrubbed, clear=True):
        s = Settings(_env_file=str(fake_env))

    assert s.google_api_key == "gkey"
    assert s.openai_api_key == "okey"
    assert s.openai_model == "gpt-x"


# ---------------------------------------------------------------------------
# Missing / empty .env file is handled gracefully
# ---------------------------------------------------------------------------


def test_missing_env_file_does_not_raise(tmp_path):
    """Pointing at a non-existent file must not raise — CI has no .env."""
    nonexistent = tmp_path / "no-such-file.env"
    s = Settings(_env_file=str(nonexistent))  # must not raise
    assert s.openai_model == "gpt-4o"         # default applies


def test_empty_env_file_uses_defaults(tmp_path):
    """An empty .env file leaves all fields at their defaults."""
    fake_env = tmp_path / ".env"
    fake_env.write_text("", encoding="utf-8")

    scrubbed = {
        k: v for k, v in os.environ.items()
        if k not in (
            "GOOGLE_API_KEY", "APP_GOOGLE_API_KEY",
            "OPENAI_API_KEY", "APP_OPENAI_API_KEY",
            "OPENAI_MODEL", "APP_OPENAI_MODEL",
        )
    }
    with patch.dict(os.environ, scrubbed, clear=True):
        s = Settings(_env_file=str(fake_env))

    assert s.google_api_key == ""
    assert s.openai_api_key == ""
    assert s.openai_model == "gpt-4o"
