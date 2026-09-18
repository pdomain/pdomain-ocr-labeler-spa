"""Integration tests for ``GET /api/projects/{project_id}/review-queue``.

Spec: pdomain-ocr-synth's docs/specs/2026-09-18-one-answer-to-what-to-
review-next.md "One route, in the order the work happens".

Pattern mirrors ``tests/integration/test_page_kinds_router.py`` and
``tests/integration/test_region_proposals_router.py``'s review-queue
sections: a small multi-page project loaded through the real app, with each
journal seeded directly (no run/decision-record ceremony beyond what each
journal's own reader needs), so tests stay fast and focused on this route's
own aggregation logic.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pdomain_book_contracts.annotation import PageKind, RegionRole
from pdomain_book_tools.typography import (
    GRAPHEME_SEGMENTATION_VERSION,
    REVIEW_CONTRACT_VERSION,
    ArtifactReference,
    Evidence,
    LabelingBundle,
    LabelState,
    TypographyTaxonomy,
    TypographyTaxonomyLabel,
    WordTypography,
)

from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.page_kind.proposal_log import PageKindProposalLog
from pdomain_ocr_labeler_spa.core.page_kind.reviewed_store import PageKindReviewedStore
from pdomain_ocr_labeler_spa.core.regions.decision_log import RegionDecisionLog
from pdomain_ocr_labeler_spa.core.regions.models import Disposition, RegionDecision, RegionProposal
from pdomain_ocr_labeler_spa.core.regions.proposal_log import RegionProposalLog
from pdomain_ocr_labeler_spa.core.review_counts import PageWordCounts, WordReviewCountsJournal
from pdomain_ocr_labeler_spa.core.typography_review import (
    ImportedTextBinding,
    ImportedTextValidationLog,
    stable_page_id,
)
from pdomain_ocr_labeler_spa.core.typography_review_counts import (
    PageTypographyCounts,
    TypographyReviewCountsJournal,
)
from pdomain_ocr_labeler_spa.settings import Settings
from tests.unit.core.persistence.test_book_labeling_session import _write_book

_TOTAL_PAGES = 4
_PROJECT_ID = "book1"
_REVIEW_QUEUE = f"/api/projects/{_PROJECT_ID}/review-queue"


def _make_settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 8080,
        "config_root": tmp_path / "config",
        "data_root": tmp_path / "data",
        "cache_root": tmp_path / "cache",
        "mode": "api_only",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    root.mkdir()
    proj = root / _PROJECT_ID
    proj.mkdir()
    for i in range(1, _TOTAL_PAGES + 1):
        (proj / f"{i:03d}.png").write_bytes(b"\x89PNG\r\n")
    return root


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post("/api/projects/load", json={"project_root": str(projects_root / _PROJECT_ID)})
        assert resp.status_code == 200, resp.text
        yield c


def _project_root(client: TestClient) -> Path:
    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    loaded = project_state.loaded_project
    assert loaded is not None
    return loaded.project_root  # type: ignore[no-any-return]


def _kind(body: dict[str, Any], name: str) -> dict[str, Any]:
    return next(entry for entry in body["kinds"] if entry["kind"] == name)


# ── Seed helpers ────────────────────────────────────────────────────────────


def _seed_region_proposal(
    project_root: Path, *, proposal_id: str, page_index: int = 0, run_id: str = "r1"
) -> None:
    RegionProposalLog(project_root).append_proposals(
        [
            RegionProposal(
                proposal_id=proposal_id,
                run_id=run_id,
                page_index=page_index,
                role=RegionRole.POETRY,
                box=(5, 5, 50, 50),
                confidence=0.8,
                evidence={},
            )
        ]
    )


def _accept_proposal(project_root: Path, *, proposal_id: str, region_id: str, run_id: str = "r1") -> None:
    RegionDecisionLog(project_root).append(
        RegionDecision(
            decision_id=f"d-{proposal_id}",
            run_id=run_id,
            proposal_id=proposal_id,
            disposition=Disposition.ACCEPTED,
            region_id=region_id,
            actor="default",
            decided_at="2026-09-08T10:00:00+00:00",
        )
    )


def _seed_word_counts(
    project_root: Path, *, page_index: int, total_words: int, validated_words: int, content_hash: str = "h"
) -> None:
    WordReviewCountsJournal(project_root).append(
        PageWordCounts(
            page_index=page_index,
            content_hash=content_hash,
            total_words=total_words,
            validated_words=validated_words,
        )
    )


def _seed_typography_counts(
    project_root: Path, *, page_index: int, total_words: int, typography_reviewed_words: int
) -> None:
    """Append one rollup row keyed by ``stable_page_id`` — an ordinary project's key.

    Mirrors ``_seed_word_counts``: the review-queue route reads
    ``TypographyReviewCountsJournal`` directly, the same way it reads
    ``WordReviewCountsJournal`` for the ``word`` kind, so seeding this
    rollup row is what stands in for a real
    ``append_typography_correction`` call in these fast, route-focused
    tests.
    """
    _seed_typography_counts_for_page_id(
        project_root,
        logical_page_id=stable_page_id(project_id=_PROJECT_ID, page_index=page_index),
        total_words=total_words,
        typography_reviewed_words=typography_reviewed_words,
    )


def _seed_typography_counts_for_page_id(
    project_root: Path, *, logical_page_id: str, total_words: int, typography_reviewed_words: int
) -> None:
    """Append one rollup row under an explicit key — a labeling-bundle project's own ``page_id``."""
    TypographyReviewCountsJournal(project_root).append(
        PageTypographyCounts(
            logical_page_id=logical_page_id,
            total_words=total_words,
            typography_reviewed_words=typography_reviewed_words,
        )
    )


# ── Shape and ordering ───────────────────────────────────────────────────────


def test_returns_404_for_an_unloaded_project(loaded_client: TestClient) -> None:
    resp = loaded_client.get("/api/projects/other_book/review-queue")
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"] == "project_not_found"


def test_kinds_are_returned_in_the_order_the_work_happens(loaded_client: TestClient) -> None:
    resp = loaded_client.get(_REVIEW_QUEUE)
    assert resp.status_code == 200, resp.text
    assert [entry["kind"] for entry in resp.json()["kinds"]] == [
        "page_kind",
        "region",
        "word",
        "typography",
        "glyph",
    ]


def test_glyph_is_unavailable_with_a_reason(loaded_client: TestClient) -> None:
    resp = loaded_client.get(_REVIEW_QUEUE)
    glyph = _kind(resp.json(), "glyph")
    assert glyph["available"] is False
    assert glyph["outstanding"] == 0
    assert glyph["total"] == 0
    assert glyph["unavailable_reason"]


# ── page_kind ────────────────────────────────────────────────────────────────


def test_page_kind_outstanding_counts_unreviewed_pages(loaded_client: TestClient) -> None:
    project_root = _project_root(loaded_client)
    PageKindReviewedStore(project_root).mark_reviewed(
        0, "2026-09-08T10:00:00+00:00", kind=PageKind.TITLE_PAGE, method="single"
    )

    resp = loaded_client.get(_REVIEW_QUEUE)
    page_kind = _kind(resp.json(), "page_kind")

    assert page_kind["total"] == _TOTAL_PAGES
    assert page_kind["outstanding"] == _TOTAL_PAGES - 1
    assert page_kind["first_page_index"] == 1
    assert page_kind["blocked_by"] is None
    assert page_kind["available"] is True


def test_page_kind_first_page_index_is_none_when_every_page_is_reviewed(loaded_client: TestClient) -> None:
    project_root = _project_root(loaded_client)
    store = PageKindReviewedStore(project_root)
    for idx in range(_TOTAL_PAGES):
        store.mark_reviewed(idx, "2026-09-08T10:00:00+00:00", kind=PageKind.BODY, method="single")

    resp = loaded_client.get(_REVIEW_QUEUE)
    page_kind = _kind(resp.json(), "page_kind")

    assert page_kind["outstanding"] == 0
    assert page_kind["first_page_index"] is None


# ── region ───────────────────────────────────────────────────────────────────


def test_region_is_blocked_by_page_kind_when_no_page_has_kind_state(loaded_client: TestClient) -> None:
    project_root = _project_root(loaded_client)
    _seed_region_proposal(project_root, proposal_id="p1")

    resp = loaded_client.get(_REVIEW_QUEUE)
    region = _kind(resp.json(), "region")

    assert region["blocked_by"] == "page_kind"


def test_region_unblocks_once_a_single_page_is_reviewed(loaded_client: TestClient) -> None:
    project_root = _project_root(loaded_client)
    _seed_region_proposal(project_root, proposal_id="p1")
    PageKindReviewedStore(project_root).mark_reviewed(
        0, "2026-09-08T10:00:00+00:00", kind=PageKind.BODY, method="single"
    )

    resp = loaded_client.get(_REVIEW_QUEUE)
    region = _kind(resp.json(), "region")

    assert region["blocked_by"] is None


def test_region_unblocks_from_a_proposed_kind_alone(loaded_client: TestClient) -> None:
    """No proposal has to be reviewed — merely proposed unblocks region work."""
    from pdomain_ocr_labeler_spa.core.page_kind.models import PageKindProposal, PageKindProposalRun

    project_root = _project_root(loaded_client)
    _seed_region_proposal(project_root, proposal_id="p1")
    log = PageKindProposalLog(project_root)
    log.append_run(
        PageKindProposalRun(
            run_id="r1",
            model_id="m",
            model_version="v1",
            created_at="2026-09-08T10:00:00+00:00",
            page_count=1,
        )
    )
    log.append_proposals(
        [
            PageKindProposal(
                proposal_id="pk1", run_id="r1", page_index=0, kind=PageKind.BODY, confidence=0.7, evidence={}
            )
        ]
    )

    resp = loaded_client.get(_REVIEW_QUEUE)
    region = _kind(resp.json(), "region")

    assert region["blocked_by"] is None


def test_region_outstanding_uses_the_shared_undecided_predicate(loaded_client: TestClient) -> None:
    project_root = _project_root(loaded_client)
    PageKindReviewedStore(project_root).mark_reviewed(
        0, "2026-09-08T10:00:00+00:00", kind=PageKind.BODY, method="single"
    )
    _seed_region_proposal(project_root, proposal_id="p-undecided", page_index=2)
    _seed_region_proposal(project_root, proposal_id="p-accepted", page_index=0)
    _accept_proposal(project_root, proposal_id="p-accepted", region_id="region-1")

    resp = loaded_client.get(_REVIEW_QUEUE)
    region = _kind(resp.json(), "region")

    assert region["total"] == 2
    assert region["outstanding"] == 1
    assert region["first_page_index"] == 2


# ── word ─────────────────────────────────────────────────────────────────────


def test_word_reports_pages_not_counted_and_is_a_lower_bound(loaded_client: TestClient) -> None:
    project_root = _project_root(loaded_client)
    _seed_word_counts(project_root, page_index=0, total_words=5, validated_words=2)

    resp = loaded_client.get(_REVIEW_QUEUE)
    word = _kind(resp.json(), "word")

    assert word["total"] == 5
    assert word["outstanding"] == 3
    assert word["pages_not_counted"] == _TOTAL_PAGES - 1
    assert word["is_lower_bound"] is True
    assert word["first_page_index"] == 0


def test_word_is_not_a_lower_bound_once_every_page_is_counted_and_fully_validated(
    loaded_client: TestClient,
) -> None:
    project_root = _project_root(loaded_client)
    for idx in range(_TOTAL_PAGES):
        _seed_word_counts(project_root, page_index=idx, total_words=3, validated_words=3)

    resp = loaded_client.get(_REVIEW_QUEUE)
    word = _kind(resp.json(), "word")

    assert word["outstanding"] == 0
    assert word["pages_not_counted"] == 0
    assert word["is_lower_bound"] is False
    assert word["first_page_index"] is None


def test_word_newest_row_wins_when_a_page_is_saved_twice(loaded_client: TestClient) -> None:
    project_root = _project_root(loaded_client)
    _seed_word_counts(project_root, page_index=0, total_words=5, validated_words=1, content_hash="h0")
    _seed_word_counts(project_root, page_index=0, total_words=5, validated_words=5, content_hash="h1")
    for idx in range(1, _TOTAL_PAGES):
        _seed_word_counts(project_root, page_index=idx, total_words=1, validated_words=1)

    resp = loaded_client.get(_REVIEW_QUEUE)
    word = _kind(resp.json(), "word")

    assert word["outstanding"] == 0
    assert word["pages_not_counted"] == 0


def test_word_zero_words_are_not_counted_as_done_without_a_confirmed_blank_kind(
    loaded_client: TestClient,
) -> None:
    """BUG-RELOAD-1: reload OCR can legitimately return zero words for a page.

    Until a person confirms that page's kind as blank, the zero must not
    read as satisfied review work — it is indistinguishable, from the count
    alone, from OCR failing to find text a person can plainly see.
    """
    project_root = _project_root(loaded_client)
    _seed_word_counts(project_root, page_index=0, total_words=0, validated_words=0)
    for idx in range(1, _TOTAL_PAGES):
        _seed_word_counts(project_root, page_index=idx, total_words=1, validated_words=1)

    resp = loaded_client.get(_REVIEW_QUEUE)
    word = _kind(resp.json(), "word")

    assert word["total"] == _TOTAL_PAGES - 1
    assert word["outstanding"] == 0
    assert word["pages_not_counted"] == 1
    assert word["is_lower_bound"] is True
    assert word["first_page_index"] == 0


def test_word_zero_words_count_as_done_once_the_page_kind_is_confirmed_blank(
    loaded_client: TestClient,
) -> None:
    project_root = _project_root(loaded_client)
    PageKindReviewedStore(project_root).mark_reviewed(
        0, "2026-09-08T10:00:00+00:00", kind=PageKind.BLANK, method="single"
    )
    _seed_word_counts(project_root, page_index=0, total_words=0, validated_words=0)
    for idx in range(1, _TOTAL_PAGES):
        _seed_word_counts(project_root, page_index=idx, total_words=1, validated_words=1)

    resp = loaded_client.get(_REVIEW_QUEUE)
    word = _kind(resp.json(), "word")

    assert word["total"] == _TOTAL_PAGES - 1
    assert word["outstanding"] == 0
    assert word["pages_not_counted"] == 0
    assert word["is_lower_bound"] is False
    assert word["first_page_index"] is None


# ── typography ───────────────────────────────────────────────────────────────


def test_typography_is_blocked_by_word_when_words_are_outstanding(loaded_client: TestClient) -> None:
    project_root = _project_root(loaded_client)
    _seed_word_counts(project_root, page_index=0, total_words=5, validated_words=2)

    resp = loaded_client.get(_REVIEW_QUEUE)
    typography = _kind(resp.json(), "typography")

    assert typography["blocked_by"] == "word"
    assert typography["first_page_index"] == _kind(resp.json(), "word")["first_page_index"]
    assert typography["is_lower_bound"] is True


def test_typography_is_blocked_by_word_while_any_page_is_uncounted(loaded_client: TestClient) -> None:
    """Every counted page is fully validated, but not every page is counted —
    the word kind reports ``outstanding: 0`` yet typography must still wait.
    """
    project_root = _project_root(loaded_client)
    _seed_word_counts(project_root, page_index=0, total_words=3, validated_words=3)

    resp = loaded_client.get(_REVIEW_QUEUE)
    word = _kind(resp.json(), "word")
    typography = _kind(resp.json(), "typography")

    assert word["outstanding"] == 0
    assert word["pages_not_counted"] > 0
    assert typography["blocked_by"] == "word"


def test_typography_unblocks_and_counts_outstanding_from_the_rollup(loaded_client: TestClient) -> None:
    project_root = _project_root(loaded_client)
    for idx in range(_TOTAL_PAGES):
        _seed_word_counts(project_root, page_index=idx, total_words=1, validated_words=1)
        # Page 0's one word is typography-reviewed; the other three pages' are not.
        _seed_typography_counts(
            project_root, page_index=idx, total_words=1, typography_reviewed_words=1 if idx == 0 else 0
        )

    resp = loaded_client.get(_REVIEW_QUEUE)
    typography = _kind(resp.json(), "typography")

    assert typography["blocked_by"] is None
    assert typography["total"] == _TOTAL_PAGES
    assert typography["outstanding"] == _TOTAL_PAGES - 1
    assert typography["first_page_index"] == 1
    assert typography["pages_not_counted"] == 0
    assert typography["is_lower_bound"] is True


def test_typography_incomplete_replacement_is_not_counted_when_unblocked(loaded_client: TestClient) -> None:
    project_root = _project_root(loaded_client)
    for idx in range(_TOTAL_PAGES):
        _seed_word_counts(project_root, page_index=idx, total_words=1, validated_words=1)
        _seed_typography_counts(project_root, page_index=idx, total_words=1, typography_reviewed_words=0)

    resp = loaded_client.get(_REVIEW_QUEUE)
    typography = _kind(resp.json(), "typography")

    assert typography["blocked_by"] is None
    assert typography["outstanding"] == _TOTAL_PAGES


def test_typography_reads_a_small_rollup_regardless_of_the_corrections_journal_size(
    loaded_client: TestClient,
) -> None:
    """docs/issues/2026-09-18-typography-numerator-needs-a-per-page-rollup.md:
    before the rollup, this entry answered its count by reading and parsing
    the whole ``typography-corrections.jsonl``, at about 80 microseconds a
    row, and refused to compute a count at all above 512 KiB. The rollup
    removes that ceiling — a corrections journal far past the old limit
    coexists here with a small, accurate rollup, and the route reports a
    real count from the rollup alone. The planted bytes need not be valid
    JSON: the route must never open this file to answer ``typography``.
    """
    project_root = _project_root(loaded_client)
    for idx in range(_TOTAL_PAGES):
        _seed_word_counts(project_root, page_index=idx, total_words=1, validated_words=1)
        _seed_typography_counts(
            project_root, page_index=idx, total_words=1, typography_reviewed_words=1 if idx == 0 else 0
        )
    path = project_root / ".pd-pages" / "typography-corrections.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * (512 * 1024 + 4096))  # past the old 512 KiB availability ceiling

    resp = loaded_client.get(_REVIEW_QUEUE)
    typography = _kind(resp.json(), "typography")

    assert typography["available"] is True
    assert typography["blocked_by"] is None
    assert typography["total"] == _TOTAL_PAGES
    assert typography["outstanding"] == _TOTAL_PAGES - 1
    assert typography["first_page_index"] == 1


def test_typography_reports_pages_not_counted_for_pages_with_no_rollup_row(loaded_client: TestClient) -> None:
    """A page can be fully word-validated yet have no typography rollup row
    of its own — either untouched, or corrected before this rollup existed.
    The two are indistinguishable from a rollup-only read, so neither is
    reported as a confidently wrong zero: the page is excluded from
    ``total``/``outstanding`` and surfaced through ``pages_not_counted``,
    mirroring how ``word`` already treats a page it has never saved.
    """
    project_root = _project_root(loaded_client)
    for idx in range(_TOTAL_PAGES):
        _seed_word_counts(project_root, page_index=idx, total_words=2, validated_words=2)
    _seed_typography_counts(project_root, page_index=0, total_words=2, typography_reviewed_words=2)
    # Pages 1..3 are fully word-validated but have no typography rollup row.

    resp = loaded_client.get(_REVIEW_QUEUE)
    typography = _kind(resp.json(), "typography")

    assert typography["available"] is True
    assert typography["blocked_by"] is None
    assert typography["total"] == 2
    assert typography["outstanding"] == 0
    assert typography["pages_not_counted"] == 3
    assert typography["is_lower_bound"] is True


def test_typography_reviewed_count_drops_when_the_newest_rollup_row_is_lower(
    loaded_client: TestClient,
) -> None:
    """A revision that un-reviews a previously-reviewed word must lower the
    page's rolled-up count — the newest row always wins, never a running
    delta (docs/issues/2026-09-18-typography-numerator-needs-a-per-page-
    rollup.md "What it would cost to build").
    """
    project_root = _project_root(loaded_client)
    for idx in range(_TOTAL_PAGES):
        _seed_word_counts(project_root, page_index=idx, total_words=1, validated_words=1)
        _seed_typography_counts(project_root, page_index=idx, total_words=1, typography_reviewed_words=0)
    _seed_typography_counts(project_root, page_index=0, total_words=1, typography_reviewed_words=1)

    resp = loaded_client.get(_REVIEW_QUEUE)
    assert _kind(resp.json(), "typography")["outstanding"] == _TOTAL_PAGES - 1

    # A later revision on page 0 fails the completeness bar and un-reviews it.
    _seed_typography_counts(project_root, page_index=0, total_words=1, typography_reviewed_words=0)

    resp = loaded_client.get(_REVIEW_QUEUE)
    assert _kind(resp.json(), "typography")["outstanding"] == _TOTAL_PAGES


# ── one read per journal ─────────────────────────────────────────────────────


def test_review_queue_reads_each_journal_once_per_request(
    loaded_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = _project_root(loaded_client)
    PageKindReviewedStore(project_root).mark_reviewed(
        0, "2026-09-08T10:00:00+00:00", kind=PageKind.BODY, method="single"
    )
    _seed_region_proposal(project_root, proposal_id="p1", page_index=0)
    _seed_region_proposal(project_root, proposal_id="p2", page_index=1)
    _accept_proposal(project_root, proposal_id="p1", region_id="region-1")
    for idx in range(_TOTAL_PAGES):
        _seed_word_counts(project_root, page_index=idx, total_words=2, validated_words=2)
    _seed_typography_counts(project_root, page_index=0, total_words=2, typography_reviewed_words=2)

    counts: dict[str, int] = {}

    def _counted(cls: type, name: str, key: str) -> None:
        original = getattr(cls, name)
        counts[key] = 0

        def _wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
            counts[key] += 1
            return original(self, *args, **kwargs)

        monkeypatch.setattr(cls, name, _wrapped)

    _counted(PageKindProposalLog, "_read", "page_kind_proposals")
    _counted(PageKindReviewedStore, "_read", "page_kind_reviewed")
    _counted(RegionProposalLog, "_read", "region_proposals")
    _counted(RegionDecisionLog, "decisions", "region_decisions")
    _counted(WordReviewCountsJournal, "_read_locked", "word_counts")
    _counted(TypographyReviewCountsJournal, "_read_locked", "typography_review_counts")

    resp = loaded_client.get(_REVIEW_QUEUE)

    assert resp.status_code == 200, resp.text
    assert counts == {
        "page_kind_proposals": 1,
        "page_kind_reviewed": 1,
        "region_proposals": 1,
        "region_decisions": 1,
        "word_counts": 1,
        "typography_review_counts": 1,
    }


# ── Labeling-bundle project shapes ───────────────────────────────────────────
#
# A project loaded from a labeling bundle validates word text through
# ``ImportedTextValidationLog``, never ``save_page_content_to_store`` — see
# ``api/review_queue.py``'s ``_word_entry``. Two shapes:
#
# - A single-page ``labeling-bundle.json`` project: the bundle is resident,
#   its word list and validation journal are counted from directly.
# - A multi-page ``book-labeling-manifest.json`` project (a "book labeling
#   session"): each page's word total lives only in that page's own
#   materialized bundle, unreachable without opening it, so ``word`` (and
#   therefore ``typography``) reports unavailable.


def _make_bundle_settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "host": "127.0.0.1",
        "port": 8080,
        "config_root": tmp_path / "config",
        "data_root": tmp_path / "data",
        "cache_root": tmp_path / "cache",
        "mode": "api_only",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _write_bundle_project(root: Path, *, word_texts: list[str]) -> LabelingBundle:
    """A single-page ``labeling-bundle.json`` project with the given words.

    Mirrors ``tests/integration/test_projects_router.py``'s
    ``_write_labeling_bundle_project``, parameterized on word count so the
    ``word`` entry has more than one word to be partly outstanding on.
    """
    root.mkdir()
    artifacts = root / "artifacts"
    artifacts.mkdir()
    image_payload = b"image-payload"
    (artifacts / "images").mkdir()
    (artifacts / "images" / "001.png").write_bytes(image_payload)
    image_sha = hashlib.sha256(image_payload).hexdigest()
    page_payload = b"page-record"
    (artifacts / "page-record.json").write_bytes(page_payload)
    page_sha = hashlib.sha256(page_payload).hexdigest()
    page_id = "pgdp:bundle-project:001.png"
    page_head_payload = (
        json.dumps(
            {
                "configuration_hash": "c" * 64,
                "image_sha256": image_sha,
                "page_id": page_id,
                "page_sha256": page_sha,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    taxonomy = TypographyTaxonomy(
        version="labeler-v1",
        labels=(
            TypographyTaxonomyLabel(
                value="italic", display_name="Italic", required_for_completion=True, trainable=True
            ),
        ),
    )
    words = tuple(
        WordTypography(
            word_id=f"7ca20136-634e-5282-a071-{index:012d}",
            text=text,
            text_sha256=hashlib.sha256(text.encode()).hexdigest(),
            page_content_sha256=page_sha,
            image_artifact_sha256=image_sha,
            grapheme_map_version=GRAPHEME_SEGMENTATION_VERSION,
            taxonomy_version=taxonomy.version,
            taxonomy_hash=taxonomy.taxonomy_hash,
            label_states={"italic": LabelState.UNKNOWN},
            source_evidence_ids=("source-evidence",),
        )
        for index, text in enumerate(word_texts)
    )
    bundle = LabelingBundle(
        schema_version=REVIEW_CONTRACT_VERSION,
        configuration_hash="c" * 64,
        taxonomy=taxonomy,
        page_id=page_id,
        page_sha256=page_sha,
        image_sha256=image_sha,
        text_sha256=hashlib.sha256(" ".join(word_texts).encode()).hexdigest(),
        page_head_sha256=hashlib.sha256(page_head_payload).hexdigest(),
        artifacts=(
            ArtifactReference(
                artifact_id="image", relative_path="images/001.png", sha256=image_sha, media_type="image/png"
            ),
            ArtifactReference(
                artifact_id="page-record",
                relative_path="page-record.json",
                sha256=page_sha,
                media_type="application/json",
            ),
        ),
        evidence=(
            Evidence(
                evidence_id="source-evidence",
                artifact_id="image",
                artifact_sha256=image_sha,
                byte_start=0,
                byte_end=1,
            ),
        ),
        words=words,
    )
    (root / "labeling-bundle.json").write_text(bundle.model_dump_json(indent=2))
    return bundle


def _load_bundle_project(tmp_path: Path, bundle_root: Path) -> TestClient:
    settings = _make_bundle_settings(tmp_path, source_projects_root=bundle_root.parent)
    app = build_app(settings)
    client = TestClient(app)
    client.__enter__()
    resp = client.post("/api/projects/load", json={"project_root": str(bundle_root)})
    assert resp.status_code == 200, resp.text
    return client


def _validate_bundle_word(
    project_root: Path, bundle: LabelingBundle, word: WordTypography, *, validated: bool
) -> None:
    assert bundle.bundle_id is not None
    binding = ImportedTextBinding(
        bundle_id=bundle.bundle_id,
        page_id=bundle.page_id,
        page_sha256=bundle.page_sha256,
        page_head_sha256=bundle.page_head_sha256,
        word_id=word.word_id,
        text=word.text,
        text_sha256=word.text_sha256,
    )
    log = ImportedTextValidationLog(project_root, corpus_root=project_root.parent)
    head = log.head(binding)
    log.append(binding, validated=validated, expected_head=head.head_token)


def test_word_counts_a_single_bundle_project_from_the_real_thing(tmp_path: Path) -> None:
    (tmp_path / "projects").mkdir()
    bundle_root = tmp_path / "projects" / "bundle-project"
    bundle = _write_bundle_project(bundle_root, word_texts=["alpha", "beta", "gamma"])
    client = _load_bundle_project(tmp_path, bundle_root)
    try:
        _validate_bundle_word(bundle_root, bundle, bundle.words[0], validated=True)
        _validate_bundle_word(bundle_root, bundle, bundle.words[1], validated=True)

        resp = client.get("/api/projects/bundle-project/review-queue")
        word = _kind(resp.json(), "word")

        assert word["available"] is True
        assert word["total"] == 3
        assert word["outstanding"] == 1
        assert word["pages_not_counted"] == 0
        assert word["is_lower_bound"] is False
        assert word["first_page_index"] == 0
    finally:
        client.__exit__(None, None, None)


def test_word_reports_fully_validated_for_a_single_bundle_project(tmp_path: Path) -> None:
    (tmp_path / "projects").mkdir()
    bundle_root = tmp_path / "projects" / "bundle-project"
    bundle = _write_bundle_project(bundle_root, word_texts=["alpha", "beta"])
    client = _load_bundle_project(tmp_path, bundle_root)
    try:
        for word in bundle.words:
            _validate_bundle_word(bundle_root, bundle, word, validated=True)

        resp = client.get("/api/projects/bundle-project/review-queue")
        word = _kind(resp.json(), "word")

        assert word["outstanding"] == 0
        assert word["first_page_index"] is None
    finally:
        client.__exit__(None, None, None)


def test_typography_for_a_single_bundle_project_uses_the_bundles_page_id(tmp_path: Path) -> None:
    (tmp_path / "projects").mkdir()
    bundle_root = tmp_path / "projects" / "bundle-project"
    bundle = _write_bundle_project(bundle_root, word_texts=["alpha", "beta", "gamma"])
    client = _load_bundle_project(tmp_path, bundle_root)
    try:
        for word in bundle.words:
            _validate_bundle_word(bundle_root, bundle, word, validated=True)

        # Seed a rollup row keyed by the bundle's OWN page_id — not
        # stable_page_id(project_id, 0), which nothing writes for a bundle
        # project.
        _seed_typography_counts_for_page_id(
            bundle_root, logical_page_id=bundle.page_id, total_words=3, typography_reviewed_words=1
        )

        resp = client.get("/api/projects/bundle-project/review-queue")
        body = resp.json()
        word = _kind(body, "word")
        typography = _kind(body, "typography")

        assert word["outstanding"] == 0
        assert typography["available"] is True
        assert typography["blocked_by"] is None
        assert typography["total"] == 3
        assert typography["outstanding"] == 2
        assert typography["first_page_index"] == 0
    finally:
        client.__exit__(None, None, None)


def test_word_and_typography_are_unavailable_for_a_multi_page_labeling_bundle_book(tmp_path: Path) -> None:
    (tmp_path / "projects").mkdir()
    book_root = tmp_path / "projects" / "book-project"
    manifest = _write_book(book_root, page_count=3)
    client = _load_bundle_project(tmp_path, book_root)
    try:
        # ``_write_book``'s book_id is "book:pgdp:project" — the loader takes
        # the last colon-separated part as the project_id, not the directory
        # name (see ``api/projects.py``'s ``_build_project_from_book_labeling_
        # manifest``).
        project_id = manifest.book_id.split(":")[-1]
        resp = client.get(f"/api/projects/{project_id}/review-queue")
        body = resp.json()
        word = _kind(body, "word")
        typography = _kind(body, "typography")

        assert word["available"] is False
        assert word["outstanding"] == 0
        assert word["total"] == 0
        assert word["unavailable_reason"]

        assert typography["available"] is False
        assert typography["unavailable_reason"]
    finally:
        client.__exit__(None, None, None)
