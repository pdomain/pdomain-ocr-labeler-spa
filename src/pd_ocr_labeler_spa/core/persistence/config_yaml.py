"""``config.yaml`` reader / writer — spec §7.

Spec authority: ``docs/architecture/09-persistence.md §7``.

The file lives at ``<config_root>/config.yaml`` (``paths.config_yaml_path``).
Single-key schema:

```yaml
source_projects_root: "/path/to/projects"
```

Design notes:

- Uses ``PyYAML`` for parse/emit (already in the project's dependency
  closure via ``uvicorn``/``anyio``). Falls back gracefully on missing or
  corrupt YAML rather than crashing.
- ``AppConfig`` uses ``extra="ignore"`` (not ``"forbid"``) so that future
  versions of the file with additional keys load cleanly on this release —
  forward-compat drift tolerance matching ``SessionState`` (D-041 / D-003).
- ``save_config`` writes via atomic rename (via ``core/persistence/atomic.py``)
  so a mid-write crash never leaves a truncated file.
- ``load_config`` NEVER raises: every failure path returns ``AppConfig()``
  with all defaults so the app boots regardless of config state.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .atomic import write_bytes_atomic
from .paths import config_yaml_path

log = logging.getLogger(__name__)


class AppConfig(BaseModel):
    """In-memory representation of ``config.yaml``.

    Forward-compat: ``extra="ignore"`` silently drops keys this version
    doesn't know about (matches ``SessionState`` D-041 contract).

    Text-normalization fields (issue #259 / spec
    ``docs/specs/2026-05-12-text-normalization-design.md``):

    - ``normalize_for_gt_matching`` — when True, the GT-matching pipeline
      normalizes OCR and GT strings before comparing (long-s, ligatures →
      ASCII). Default False (OCR fidelity wins by default, D-025).
    - ``normalize_plaintext_tabs`` — when True, plaintext tab content is
      normalized before display. Default False.
    - ``normalize_profile`` — the normalization profile name passed to
      ``pd_book_tools.text.normalize.normalize_string``. Default ``"ascii"``;
      only ``"ascii"`` is available in v1 (future: ``"gaelic"``, etc.).
    """

    model_config = ConfigDict(extra="ignore")

    source_projects_root: Path | None = None

    # Text-normalization toggles (all default False / "ascii" to match legacy
    # behaviour — pages with long-s / ligatures are stored as-is by default).
    normalize_for_gt_matching: bool = False
    normalize_plaintext_tabs: bool = False
    normalize_profile: str = "ascii"

    # Fuzzy-match threshold — mirrors legacy ``WordMatchViewModel.fuzz_threshold=0.8``
    # (``pd_ocr_labeler/viewmodels/project/word_match_view_model.py:26``).
    # Words with a fuzz score >= this threshold are classified as FUZZY rather
    # than MISMATCH.  Must be in [0.0, 1.0]; 1.0 means exact-match-only (no
    # fuzzy classification); 0.0 means everything is fuzzy.
    fuzz_threshold: float = 0.8

    # Glyph-review gate (spec §4, issue #270).
    # When True, saving a page that has words with ``glyph_annotations is None``
    # (not yet reviewed) produces a ``glyph_review_incomplete`` warning in
    # ``SavePageResponse.warnings``.  Default False (gate disabled).
    glyph_review_required: bool = False


# ──────────────────────────────────────────────────────────────────────
# Readers
# ──────────────────────────────────────────────────────────────────────


def load_config(config_root: Path) -> AppConfig:
    """Read ``<config_root>/config.yaml`` → ``AppConfig``.

    Returns ``AppConfig()`` (all defaults) on every failure mode:
    missing file, corrupt YAML, non-mapping root, Pydantic validation
    error. NEVER raises.
    """
    path = config_yaml_path(config_root)
    if not path.exists():
        return AppConfig()
    try:
        import yaml  # type: ignore[import-untyped]

        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        log.warning("config_yaml_load_failed path=%s", path, exc_info=True)
        return AppConfig()

    if not isinstance(raw, dict):
        log.warning(
            "config_yaml_non_dict_root path=%s type=%s",
            path,
            type(raw).__name__,
        )
        return AppConfig()

    try:
        return AppConfig(**raw)  # pyright: ignore[reportUnknownArgumentType] — yaml.safe_load returns untyped dict
    except Exception:
        log.warning("config_yaml_validation_failed path=%s", path, exc_info=True)
        return AppConfig()


# ──────────────────────────────────────────────────────────────────────
# Writers
# ──────────────────────────────────────────────────────────────────────


def save_config(config_root: Path, cfg: AppConfig) -> None:
    """Write ``cfg`` to ``<config_root>/config.yaml`` atomically.

    Creates ``config_root`` if it does not exist (mirrors
    ``save_session_state`` behaviour). OSError on write → re-raised to
    caller (caller is ``POST /api/projects/source-root`` which converts
    this to a 500; a config-write failure is more serious than a
    session-state failure and warrants surfacing).
    """
    import yaml  # type: ignore[import-untyped]

    path = config_yaml_path(config_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Build an ordered dict so the YAML key order is predictable.
    data: dict[str, object] = {
        "source_projects_root": (
            str(cfg.source_projects_root) if cfg.source_projects_root is not None else None
        ),
        "normalize_for_gt_matching": cfg.normalize_for_gt_matching,
        "normalize_plaintext_tabs": cfg.normalize_plaintext_tabs,
        "normalize_profile": cfg.normalize_profile,
        "fuzz_threshold": cfg.fuzz_threshold,
    }
    content = yaml.dump(data, default_flow_style=False, allow_unicode=True)
    write_bytes_atomic(path, content.encode("utf-8"))
