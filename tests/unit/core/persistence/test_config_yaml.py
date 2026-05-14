"""Unit tests for core/persistence/config_yaml.py.

Spec authority:
- ``docs/architecture/09-persistence.md §7`` — config.yaml shape + semantics.
  Single key ``source_projects_root``; auto-created on first run;
  must survive forwards-compat extras (extra="ignore").
"""

from __future__ import annotations

from pathlib import Path

from pd_ocr_labeler_spa.core.persistence.config_yaml import (
    AppConfig,
    load_config,
    save_config,
)
from pd_ocr_labeler_spa.core.persistence.paths import config_yaml_path

# ──────────────────────────────────────────────────────────────────────
# AppConfig model
# ──────────────────────────────────────────────────────────────────────


def test_app_config_defaults() -> None:
    """Default AppConfig has no source_projects_root."""
    cfg = AppConfig()
    assert cfg.source_projects_root is None


def test_app_config_round_trip(tmp_path: Path) -> None:
    """AppConfig serialises and deserialises cleanly."""
    cfg = AppConfig(source_projects_root=tmp_path / "projects")
    d = cfg.model_dump()
    cfg2 = AppConfig(**d)
    assert cfg2.source_projects_root == cfg.source_projects_root


def test_app_config_extra_fields_ignored() -> None:
    """AppConfig must not reject unknown keys (forward-compat drift tolerance)."""
    cfg = AppConfig(**{"source_projects_root": None, "unknown_future_key": "value"})
    assert cfg.source_projects_root is None


# ──────────────────────────────────────────────────────────────────────
# load_config
# ──────────────────────────────────────────────────────────────────────


def test_load_config_missing_file_returns_default(tmp_path: Path) -> None:
    """Missing config.yaml → returns AppConfig() with all defaults."""
    config_root = tmp_path / "config"
    config_root.mkdir()
    result = load_config(config_root)
    assert result is not None
    assert result.source_projects_root is None


def test_load_config_reads_source_projects_root(tmp_path: Path) -> None:
    """Populated config.yaml → source_projects_root is returned."""
    config_root = tmp_path / "config"
    config_root.mkdir()
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    path = config_yaml_path(config_root)
    path.write_text(f"source_projects_root: {str(projects_dir)!r}\n")
    result = load_config(config_root)
    assert result is not None
    assert result.source_projects_root == projects_dir


def test_load_config_invalid_yaml_returns_default(tmp_path: Path) -> None:
    """Corrupt config.yaml → returns AppConfig() defaults, no exception."""
    config_root = tmp_path / "config"
    config_root.mkdir()
    config_yaml_path(config_root).write_text("{{{{ not valid yaml")
    result = load_config(config_root)
    assert result.source_projects_root is None


def test_load_config_wrong_type_returns_default(tmp_path: Path) -> None:
    """config.yaml with non-mapping root → returns defaults, no exception."""
    config_root = tmp_path / "config"
    config_root.mkdir()
    config_yaml_path(config_root).write_text("- item1\n- item2\n")
    result = load_config(config_root)
    assert result.source_projects_root is None


def test_load_config_extra_keys_tolerated(tmp_path: Path) -> None:
    """Unknown keys in config.yaml are silently ignored (forward-compat)."""
    config_root = tmp_path / "config"
    config_root.mkdir()
    config_yaml_path(config_root).write_text("source_projects_root: null\nfuture_key: some_value\n")
    result = load_config(config_root)
    assert result.source_projects_root is None


# ──────────────────────────────────────────────────────────────────────
# save_config
# ──────────────────────────────────────────────────────────────────────


def test_save_config_creates_file(tmp_path: Path) -> None:
    """save_config writes config.yaml and the file can be loaded back."""
    config_root = tmp_path / "config"
    config_root.mkdir()
    projects = tmp_path / "projects"
    cfg = AppConfig(source_projects_root=projects)
    save_config(config_root, cfg)
    path = config_yaml_path(config_root)
    assert path.exists()
    loaded = load_config(config_root)
    assert loaded.source_projects_root == projects


def test_save_config_creates_config_root_dir(tmp_path: Path) -> None:
    """save_config creates config_root if it doesn't exist."""
    config_root = tmp_path / "config" / "subdir"
    # Not created yet.
    assert not config_root.exists()
    save_config(config_root, AppConfig())
    assert config_yaml_path(config_root).exists()


def test_save_config_round_trip_null_root(tmp_path: Path) -> None:
    """Round-trip with source_projects_root=None."""
    config_root = tmp_path / "config"
    config_root.mkdir()
    save_config(config_root, AppConfig(source_projects_root=None))
    loaded = load_config(config_root)
    assert loaded.source_projects_root is None


def test_save_config_overwrites_existing(tmp_path: Path) -> None:
    """save_config replaces existing content atomically."""
    config_root = tmp_path / "config"
    config_root.mkdir()
    first = tmp_path / "first"
    second = tmp_path / "second"
    save_config(config_root, AppConfig(source_projects_root=first))
    save_config(config_root, AppConfig(source_projects_root=second))
    loaded = load_config(config_root)
    assert loaded.source_projects_root == second
