"""Offline tests for _config.py — TOML/env loading, schema validation."""

from pathlib import Path

import pytest

import _config
from _config import (
    PLACEHOLDER_MAILTO,
    _coerce_section,
    load_config,
)


def _write_toml(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _isolate_config(monkeypatch, example: Path, local: Path) -> None:
    """Point the loader at temp files instead of the dev machine's real configs."""
    monkeypatch.setattr(_config, "EXAMPLE_TOML", example)
    monkeypatch.setattr(_config, "LOCAL_TOML", local)
    for env in (
        "REF_DOWNLOADER_MAILTO",
        "REF_DOWNLOADER_ZOTERO_DB",
        "REF_DOWNLOADER_EDGE_PROFILE",
        "REF_DOWNLOADER_DISABLE_EXTENSIONS",
        "REF_DOWNLOADER_CONFIG",
    ):
        monkeypatch.delenv(env, raising=False)


def test_load_with_only_example_yields_placeholder(monkeypatch, tmp_path):
    example = tmp_path / "config.example.toml"
    local = tmp_path / "config.local.toml"  # does not exist
    _write_toml(example, '[crossref]\nmailto = "your.email@example.com"\n')
    _isolate_config(monkeypatch, example, local)

    cfg = load_config()

    assert cfg.crossref.mailto == PLACEHOLDER_MAILTO
    assert cfg.zotero.db_path == ""
    assert cfg.institution.auth_hosts == []
    assert cfg.institution.ignored_access_dois == []


def test_local_overrides_example(monkeypatch, tmp_path):
    example = tmp_path / "config.example.toml"
    local = tmp_path / "config.local.toml"
    _write_toml(example, '[crossref]\nmailto = "default@example.com"\n')
    _write_toml(local, '[crossref]\nmailto = "real@uni.edu"\n')
    _isolate_config(monkeypatch, example, local)

    cfg = load_config()

    assert cfg.crossref.mailto == "real@uni.edu"


def test_env_var_overrides_file(monkeypatch, tmp_path):
    example = tmp_path / "config.example.toml"
    local = tmp_path / "config.local.toml"
    _write_toml(example, '[crossref]\nmailto = "default@example.com"\n')
    _write_toml(local, '[crossref]\nmailto = "real@uni.edu"\n')
    _isolate_config(monkeypatch, example, local)
    monkeypatch.setenv("REF_DOWNLOADER_MAILTO", "env@override.com")

    cfg = load_config()

    assert cfg.crossref.mailto == "env@override.com"


def test_malformed_toml_exits_with_code_2(monkeypatch, tmp_path, capsys):
    """Bad TOML should produce a friendly stderr message + exit(2), not a stack trace."""
    bad = tmp_path / "bad.toml"
    bad.write_bytes(b"this is = not valid TOML [[[\n")
    _isolate_config(
        monkeypatch,
        tmp_path / "nonexistent_example.toml",
        tmp_path / "nonexistent_local.toml",
    )

    with pytest.raises(SystemExit) as exc_info:
        load_config(bad)

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "Failed to parse TOML" in captured.err


def test_schema_drops_non_strings_in_list(monkeypatch, tmp_path, capsys):
    """auth_hosts = ['valid', 123, true, 'another'] should keep only strings + warn."""
    example = tmp_path / "config.example.toml"
    local = tmp_path / "config.local.toml"
    _write_toml(example, '[crossref]\nmailto = "x@y.com"\n')
    _write_toml(
        local,
        '[institution]\nauth_hosts = ["valid", 123, true, "another"]\n',
    )
    _isolate_config(monkeypatch, example, local)

    cfg = load_config()

    assert cfg.institution.auth_hosts == ["valid", "another"]
    assert "2 non-string entries" in capsys.readouterr().err


def test_coerce_section_rejects_scalar_section(capsys):
    """When a top-level key is a scalar string instead of a table, coerce returns {}."""
    result = _coerce_section({"institution": "should_be_table"}, "institution")

    assert result == {}
    assert "expected a table" in capsys.readouterr().err
