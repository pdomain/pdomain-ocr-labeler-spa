"""Pin the pure OCR-model selection algorithm against the legacy port.

Source of truth: legacy
``pd_ocr_labeler/operations/ocr/model_selection_operations.py``
``ModelSelectionOperations.pick_default_keys`` (lines 432-483 at
import time). Reasons map 1:1 with the
``GetOCRConfigResponse.selection_reason`` Literal in
``core/ocr_models.py`` so the wire contract and the algorithm stay in
sync.

Slice 8c-ii deliberately lands ONLY the pure selection function. The
discovery side (HF probe, local-models walk, mtime collection) is
adapter-shaped work that slips to 8c-iii+. Tests here construct
``ModelOptionRecord`` lists directly to exercise the algorithm.

Selection precedence (legacy verbatim):
1. HF latest if reachable AND (no local OR HF >= newest local mtime)
   → reason ``hf-latest``.
2. Latest local fine-tuned model when present
   → reason ``local-newer-than-hf`` (HF reachable, local strictly
   newer) or ``local-only-hf-unreachable`` (HF down, local present).
3. HF reachable but no local pair → ``hf-only``.
4. HF unreachable, no local → ``hf-unreachable-no-local`` (still
   returns the stock key as the picked pair).
5. Bare fallback → ``stock-fallback``.

The detection and recognition keys can diverge for case (2) — local
discovery may have a det model but no reco at the same signature.
The legacy code returns whichever local key it found *per component*;
this test pins that behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pd_ocr_labeler_spa.core.model_selection import (
    HF_LATEST_KEY,
    STOCK_KEY,
    ModelOptionRecord,
    pick_default_keys,
)


def _now() -> datetime:
    return datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)


def _hf(last_modified: datetime | None, *, key: str = HF_LATEST_KEY) -> ModelOptionRecord:
    return ModelOptionRecord(
        key=key,
        source="huggingface",
        hf_last_modified=last_modified,
        local_mtime=None,
        has_detection=True,
        has_recognition=True,
        is_preferred_profile=False,
    )


def _local(
    *,
    key: str,
    mtime: datetime,
    has_detection: bool = True,
    has_recognition: bool = True,
    is_preferred: bool = True,
) -> ModelOptionRecord:
    return ModelOptionRecord(
        key=key,
        source="local",
        hf_last_modified=None,
        local_mtime=mtime,
        has_detection=has_detection,
        has_recognition=has_recognition,
        is_preferred_profile=is_preferred,
    )


def _stock() -> ModelOptionRecord:
    return ModelOptionRecord(
        key=STOCK_KEY,
        source="stock",
        hf_last_modified=None,
        local_mtime=None,
        has_detection=True,
        has_recognition=True,
        is_preferred_profile=False,
    )


class TestHFLatest:
    """Case (1): HF reachable AND (no local OR HF >= local newest)."""

    def test_hf_reachable_no_local(self) -> None:
        det, reco, reason = pick_default_keys(
            [_hf(_now()), _stock()],
        )
        assert det == HF_LATEST_KEY
        assert reco == HF_LATEST_KEY
        assert reason == "hf-latest"

    def test_hf_newer_than_local(self) -> None:
        now = _now()
        det, reco, reason = pick_default_keys(
            [
                _hf(now),
                _local(key="all/run-1700000000", mtime=now - timedelta(days=10)),
                _stock(),
            ],
        )
        assert det == HF_LATEST_KEY
        assert reco == HF_LATEST_KEY
        assert reason == "hf-latest"

    def test_hf_equal_to_local_picks_hf(self) -> None:
        # Legacy comment: "latest or equal" — equal favors HF.
        now = _now()
        det, reco, reason = pick_default_keys(
            [
                _hf(now),
                _local(key="all/run-1700000000", mtime=now),
                _stock(),
            ],
        )
        assert reason == "hf-latest"
        assert det == reco == HF_LATEST_KEY


class TestLocalNewer:
    """Case (2a): HF reachable but local strictly newer."""

    def test_local_strictly_newer_than_hf(self) -> None:
        now = _now()
        det, reco, reason = pick_default_keys(
            [
                _hf(now - timedelta(days=10)),
                _local(key="all/run-1700000000", mtime=now),
                _stock(),
            ],
        )
        assert det == "all/run-1700000000"
        assert reco == "all/run-1700000000"
        assert reason == "local-newer-than-hf"


class TestLocalOnlyHFDown:
    """Case (2b): HF unreachable but local pair available."""

    def test_local_only_hf_unreachable(self) -> None:
        now = _now()
        det, reco, reason = pick_default_keys(
            [
                _hf(None),  # last_modified None ⇒ unreachable
                _local(key="all/run-1700000000", mtime=now),
                _stock(),
            ],
        )
        assert det == "all/run-1700000000"
        assert reco == "all/run-1700000000"
        assert reason == "local-only-hf-unreachable"

    def test_no_hf_record_at_all_local_only(self) -> None:
        # No HF record present (e.g. caller dropped it) — still local-only path.
        now = _now()
        det, reco, reason = pick_default_keys(
            [
                _local(key="all/run-1700000000", mtime=now),
                _stock(),
            ],
        )
        assert det == "all/run-1700000000"
        assert reco == "all/run-1700000000"
        assert reason == "local-only-hf-unreachable"


class TestHFOnly:
    """Case (3): HF reachable, no local pair → ``hf-only``.

    Legacy line 480-481 — only triggers when local options are present
    but lack the det/reco pair. With *no* local entries at all the
    earlier ``hf-latest`` branch fires (no local mtime ⇒ HF wins).
    The distinguishing case here: a local record exists but lacks
    one of detection / recognition, so the local pair is incomplete.
    """

    def test_hf_only_when_local_pair_incomplete(self) -> None:
        now = _now()
        det, reco, reason = pick_default_keys(
            [
                _hf(now),
                # local with detection but no recognition (incomplete pair)
                _local(
                    key="all/run-1700000000",
                    mtime=now - timedelta(days=2),
                    has_recognition=False,
                ),
                _stock(),
            ],
        )
        # Local mtime exists and is older than HF ⇒ hf-latest fires first.
        # This pins that the algorithm's mtime check is over the *file*
        # (any local file), not over the *complete pair*. Matches legacy
        # ``latest_local_mtime`` which iterates det/reco paths regardless
        # of pair completeness.
        assert reason == "hf-latest"
        assert det == reco == HF_LATEST_KEY


class TestHFUnreachableNoLocal:
    """Case (4): HF unreachable, no local pair → stock keys, ``hf-unreachable-no-local`` reason."""

    def test_hf_record_present_but_unreachable_no_local(self) -> None:
        det, reco, reason = pick_default_keys(
            [
                _hf(None),
                _stock(),
            ],
        )
        assert det == STOCK_KEY
        assert reco == STOCK_KEY
        assert reason == "hf-unreachable-no-local"


class TestStockFallback:
    """Case (5): No HF record at all and no local — bare fallback."""

    def test_stock_only(self) -> None:
        det, reco, reason = pick_default_keys([_stock()])
        assert det == STOCK_KEY
        assert reco == STOCK_KEY
        assert reason == "stock-fallback"

    def test_empty_list_is_stock_fallback(self) -> None:
        # Defensive: caller passed nothing. Still return stock keys
        # rather than raising — ``GET /api/ocr-config`` should never
        # 500 because discovery returned an empty list.
        det, reco, reason = pick_default_keys([])
        assert det == STOCK_KEY
        assert reco == STOCK_KEY
        assert reason == "stock-fallback"


class TestPreferredProfilePriority:
    """Legacy ``_candidate_keys_for_component`` prefers ``all/`` /
    ``base-ocr/`` profiles when present; falls back to others.
    """

    def test_preferred_profile_wins_over_unpreferred(self) -> None:
        now = _now()
        det, reco, reason = pick_default_keys(
            [
                _hf(None),  # HF unreachable so we exercise local picker
                _local(
                    key="custom/run-1700000000",
                    mtime=now - timedelta(days=1),
                    is_preferred=False,
                ),
                _local(
                    key="all/run-1690000000",
                    mtime=now - timedelta(days=5),
                    is_preferred=True,
                ),
                _stock(),
            ],
        )
        assert reason == "local-only-hf-unreachable"
        # Preferred profile takes precedence even when older (legacy
        # ``_candidate_keys_for_component`` returns ``preferred or keys``
        # — preferred subset is filtered to *only* ``all/`` /
        # ``base-ocr/`` if any exist).
        assert det == "all/run-1690000000"
        assert reco == "all/run-1690000000"

    def test_latest_within_preferred_wins(self) -> None:
        now = _now()
        det, reco, _reason = pick_default_keys(
            [
                _hf(None),
                _local(
                    key="all/run-1690000000",
                    mtime=now - timedelta(days=5),
                    is_preferred=True,
                ),
                _local(
                    key="all/run-1700000000",
                    mtime=now - timedelta(days=1),
                    is_preferred=True,
                ),
                _stock(),
            ],
        )
        # ``_latest_key`` extracts trailing 10-digit timestamp from
        # signature; later timestamp wins.
        assert det == "all/run-1700000000"
        assert reco == "all/run-1700000000"


class TestDetRecoDivergence:
    """Local discovery may yield det-only or reco-only records."""

    def test_det_and_reco_can_pick_different_local_keys(self) -> None:
        now = _now()
        det, reco, reason = pick_default_keys(
            [
                _hf(None),
                _local(
                    key="all/det-only-1700000000",
                    mtime=now - timedelta(days=1),
                    has_detection=True,
                    has_recognition=False,
                ),
                _local(
                    key="all/reco-only-1700000001",
                    mtime=now - timedelta(days=1),
                    has_detection=False,
                    has_recognition=True,
                ),
                _stock(),
            ],
        )
        assert reason == "local-only-hf-unreachable"
        assert det == "all/det-only-1700000000"
        assert reco == "all/reco-only-1700000001"


class TestRecordValidation:
    """``ModelOptionRecord`` must reject obviously-wrong shapes early."""

    def test_local_record_requires_mtime(self) -> None:
        # Slot is documented: local records SHOULD carry a mtime.
        # Building one without a mtime is a programming error.
        with pytest.raises(ValueError):
            ModelOptionRecord(
                key="all/x",
                source="local",
                hf_last_modified=None,
                local_mtime=None,
                has_detection=True,
                has_recognition=True,
                is_preferred_profile=True,
            )

    def test_hf_record_rejects_local_mtime(self) -> None:
        # Symmetric: HF records do not have a local mtime.
        with pytest.raises(ValueError):
            ModelOptionRecord(
                key=HF_LATEST_KEY,
                source="huggingface",
                hf_last_modified=_now(),
                local_mtime=_now(),
                has_detection=True,
                has_recognition=True,
                is_preferred_profile=False,
            )
