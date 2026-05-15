"""Unit tests for line-mutation endpoints (spec-23-D1, issue #317).

Spec authority:
- ``specs/23-page-payload-backend.md §9`` — line-mutation endpoints
  (``copy-gt-to-ocr`` / ``copy-ocr-to-gt`` / ``validate`` / ``delete`` /
  ``merge`` / ``split-after-word`` / ``split-by-words`` / ``refine-batch``).
- ``specs/23-page-payload-backend.md §11`` — refine is a 202+job_id;
  spec-23-D1's ``refine-batch`` enqueues the existing refine job.
- ``specs/23-page-payload-backend.md §12-§13`` — autosave + per-page lock.

Endpoints under test (8):

1. ``POST .../lines/{li}/copy-gt-to-ocr`` — ``Block.copy_ground_truth_to_ocr()``
2. ``POST .../lines/{li}/copy-ocr-to-gt`` — ``Block.copy_ocr_to_ground_truth()``
3. ``POST .../lines/{li}/validate`` — sets ``Block.is_validated`` on the
   line and on every contained word (workaround for pd-book-tools#52).
4. ``POST .../lines/{li}/delete`` — ``Page.delete_lines([li])``.
5. ``POST .../lines/merge`` — ``Page.merge_lines(line_indices)``.
6. ``POST .../lines/{li}/split-after-word`` —
   ``Page.split_line_after_word(li, wi)``.
7. ``POST .../lines/split-by-words`` —
   ``Page.split_line_with_selected_words(word_keys)`` (spec-named
   ``split_line_by_words``).
8. ``POST .../lines/refine-batch`` — enqueue refine job, return 202+job_id
   (delegates to ``api/refine.py``).

Three contract tests required by the issue:
- copy-gt-to-ocr happy-path round-trip (line words updated, gen bumped,
  cache written).
- merge of two lines (``Page.merge_lines`` invoked with the two indices,
  gen bumped, cache written).
- split-by-words producing two lines (``Page.split_line_with_selected_words``
  invoked with the (li, wi) tuples, gen bumped, cache written).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pd_ocr_labeler_spa.bootstrap import build_app
from pd_ocr_labeler_spa.core.page_state import PageLoadOutcome, PageSource
from pd_ocr_labeler_spa.core.persistence.user_page_envelope import cached_envelope_path
from pd_ocr_labeler_spa.core.project_state import PageState
from pd_ocr_labeler_spa.settings import Settings


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
    proj = root / "book1"
    proj.mkdir()
    (proj / "001.png").write_bytes(b"\x89PNG\r\n")
    (proj / "002.png").write_bytes(b"\x89PNG\r\n")
    return root


# ── Stubs ────────────────────────────────────────────────────────────────


@dataclass
class _StubWord:
    text: str = "ocr"
    ground_truth_text: str = ""
    is_validated: bool = False

    def copy_ground_truth_to_ocr(self) -> bool:
        """Mirror of ``pd_book_tools.ocr.word.Word.copy_ground_truth_to_ocr``."""
        if self.ground_truth_text:
            self.text = self.ground_truth_text
            return True
        return False

    def copy_ocr_to_ground_truth(self) -> bool:
        """Mirror of ``pd_book_tools.ocr.word.Word.copy_ocr_to_ground_truth``."""
        if self.text:
            self.ground_truth_text = self.text
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "Word",
            "text": self.text,
            "ground_truth_text": self.ground_truth_text,
            "is_validated": self.is_validated,
        }


@dataclass
class _StubLine:
    """Mimics ``pd_book_tools.ocr.block.Block`` line-level surface."""

    words: list[_StubWord] = field(default_factory=list)
    is_validated: bool = False

    def copy_ground_truth_to_ocr(self) -> bool:
        """Block.copy_ground_truth_to_ocr — copies gt→ocr for every word."""
        results = [w.copy_ground_truth_to_ocr() for w in self.words]
        return any(results)

    def copy_ocr_to_ground_truth(self) -> bool:
        """Block.copy_ocr_to_ground_truth — copies ocr→gt for every word."""
        results = [w.copy_ocr_to_ground_truth() for w in self.words]
        return any(results)


@dataclass
class _StubPage:
    """Mimics ``pd_book_tools.ocr.page.Page`` line-mutation surface."""

    lines_: list[_StubLine] = field(default_factory=list)
    label: str = "stub"

    # Recorded calls so tests can assert the route dispatched correctly.
    merge_lines_calls: list[list[int]] = field(default_factory=list)
    delete_lines_calls: list[list[int]] = field(default_factory=list)
    split_after_word_calls: list[tuple[int, int]] = field(default_factory=list)
    split_by_words_calls: list[list[tuple[int, int]]] = field(default_factory=list)

    @property
    def lines(self) -> list[_StubLine]:
        return self.lines_

    @property
    def paragraphs(self) -> list[_StubLine]:
        return self.lines_

    @property
    def words(self) -> list[_StubWord]:
        return [w for ln in self.lines_ for w in ln.words]

    def merge_lines(self, line_indices: list[int]) -> bool:
        self.merge_lines_calls.append(list(line_indices))
        if len(line_indices) < 2:
            return False
        # Pretend to merge: keep words from first line + concatenate, drop the rest.
        sorted_ix = sorted(set(line_indices))
        keep_ix = sorted_ix[0]
        all_words = [w for ix in sorted_ix for w in self.lines_[ix].words]
        new_lines = [ln for i, ln in enumerate(self.lines_) if i == keep_ix or i not in sorted_ix]
        for i, ln in enumerate(new_lines):
            if i == 0:
                ln.words = all_words
        self.lines_ = new_lines
        return True

    def delete_lines(self, line_indices: list[int]) -> bool:
        self.delete_lines_calls.append(list(line_indices))
        if not line_indices:
            return False
        drop = set(line_indices)
        self.lines_ = [ln for i, ln in enumerate(self.lines_) if i not in drop]
        return True

    def split_line_after_word(self, line_index: int, word_index: int) -> bool:
        self.split_after_word_calls.append((line_index, word_index))
        if not (0 <= line_index < len(self.lines_)):
            return False
        words = self.lines_[line_index].words
        if word_index < 0 or word_index >= len(words) - 1:
            return False
        before = words[: word_index + 1]
        after = words[word_index + 1 :]
        new_left = _StubLine(words=before)
        new_right = _StubLine(words=after)
        self.lines_ = [
            *self.lines_[:line_index],
            new_left,
            new_right,
            *self.lines_[line_index + 1 :],
        ]
        return True

    def split_line_with_selected_words(self, word_keys: list[tuple[int, int]]) -> bool:
        self.split_by_words_calls.append(list(word_keys))
        if not word_keys:
            return False
        # Group by line; lift selected words into a new line at the end.
        by_line: dict[int, set[int]] = {}
        for li, wi in word_keys:
            by_line.setdefault(li, set()).add(wi)
        selected_words: list[_StubWord] = []
        for li, wi_set in by_line.items():
            if not (0 <= li < len(self.lines_)):
                return False
            line = self.lines_[li]
            keep = [w for j, w in enumerate(line.words) if j not in wi_set]
            sel = [w for j, w in enumerate(line.words) if j in wi_set]
            line.words = keep
            selected_words.extend(sel)
        if not selected_words:
            return False
        self.lines_.append(_StubLine(words=selected_words))
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "lines": [{"words": [w.to_dict() for w in ln.words]} for ln in self.lines_],
            "paragraphs": [],
            "words": [w.to_dict() for w in self.words],
            "source_identifier": f"{self.label}.png",
        }


def _make_two_word_line(gt0: str = "", gt1: str = "") -> _StubLine:
    return _StubLine(
        words=[
            _StubWord(text="hello", ground_truth_text=gt0),
            _StubWord(text="world", ground_truth_text=gt1),
        ]
    )


def _make_two_line_page() -> _StubPage:
    """Two lines × two words each, no GT yet."""
    return _StubPage(
        lines_=[
            _make_two_word_line(),
            _make_two_word_line(),
        ],
        label="seeded",
    )


# ── Loaded-project fixture ──────────────────────────────────────────────


@pytest.fixture
def loaded_client(tmp_path: Path, projects_root: Path) -> Iterator[TestClient]:
    settings = _make_settings(tmp_path, source_projects_root=projects_root)
    app = build_app(settings)
    with TestClient(app) as c:
        resp = c.post(
            "/api/projects/load",
            json={"project_root": str(projects_root / "book1")},
        )
        assert resp.status_code == 200, resp.text
        yield c


def _seed_page_state(client: TestClient, *, page_index: int, page: _StubPage) -> PageState:
    project_state = client.app.state.project_state  # type: ignore[attr-defined]
    outcome = PageLoadOutcome(
        page_index=page_index,
        source=PageSource.OCR,
        payload=page,
    )
    pstate = PageState(page_index=page_index, page_record=outcome)
    pstate.generation = 1
    pstate.last_saved_generation = 0
    project_state._page_states[page_index] = pstate
    return pstate


# ── 1. copy-gt-to-ocr (required test) ────────────────────────────────────


def test_copy_gt_to_ocr_round_trip(loaded_client: TestClient) -> None:
    """POST /lines/{li}/copy-gt-to-ocr — gt→ocr for every word in the line.

    Asserts (spec §9 + §12 + §13):
    - 200 PagePayload response.
    - Each word's ``text`` updated to its ``ground_truth_text``.
    - ``pstate.generation`` advanced by exactly 1.
    - Cached envelope file written at the spec'd path.
    """
    # Seed line 0 with GT set on both words.
    page = _make_two_line_page()
    page.lines_[0].words[0].ground_truth_text = "GT-zero"
    page.lines_[0].words[1].ground_truth_text = "GT-one"
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    gen_before = pstate.generation

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/0/copy-gt-to-ocr",
        json={},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "book1"
    assert body["page_index"] == 0

    # gt→ocr applied to every word on line 0; line 1 untouched.
    assert page.lines_[0].words[0].text == "GT-zero"
    assert page.lines_[0].words[1].text == "GT-one"
    assert page.lines_[1].words[0].text == "hello"  # line 1 unaffected

    # Generation bumped once.
    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    pstate_after = project_state.page_states[0]
    assert pstate_after.generation == gen_before + 1

    # Cached envelope written.
    settings: Settings = loaded_client.app.state.settings  # type: ignore[attr-defined]
    expected_cache = cached_envelope_path(settings.cache_root, "book1", 0)
    assert expected_cache.exists(), f"cached envelope not written: {expected_cache}"


# ── 2. merge two lines (required test) ───────────────────────────────────


def test_merge_two_lines(loaded_client: TestClient) -> None:
    """POST /lines/merge — call Page.merge_lines with the two indices.

    Asserts (spec §9):
    - 200 PagePayload response.
    - ``Page.merge_lines`` called exactly once with ``[0, 1]``.
    - Resulting page has one line containing all four original words.
    - ``pstate.generation`` advanced by 1.
    - Cached envelope file written.
    """
    page = _make_two_line_page()
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    gen_before = pstate.generation

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/merge",
        json={"line_indices": [0, 1]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "book1"

    # pd-book-tools method invoked with the requested indices.
    assert page.merge_lines_calls == [[0, 1]]
    # After merge: one line with four words (stub preserves order).
    assert len(page.lines_) == 1
    assert len(page.lines_[0].words) == 4

    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    assert project_state.page_states[0].generation == gen_before + 1

    settings: Settings = loaded_client.app.state.settings  # type: ignore[attr-defined]
    assert cached_envelope_path(settings.cache_root, "book1", 0).exists()


# ── 3. split-by-words → two lines (required test) ────────────────────────


def test_split_by_words_produces_two_lines(loaded_client: TestClient) -> None:
    """POST /lines/split-by-words — extract the (li, wi) targets into a new line.

    Asserts (spec §9 — ``page.split_line_by_words(targets)``, actual API
    ``Page.split_line_with_selected_words``):
    - 200 PagePayload response.
    - pd-book-tools method invoked with the (li, wi) tuples.
    - Resulting page has +1 line (stub appends the extracted line).
    - ``pstate.generation`` advanced by 1.
    - Cached envelope file written.
    """
    page = _make_two_line_page()  # starts with 2 lines x 2 words
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    gen_before = pstate.generation
    lines_before = len(page.lines_)

    # Extract word (0, 1) — the second word of the first line.
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/split-by-words",
        json={"word_keys": [[0, 1]]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "book1"

    # pd-book-tools method invoked.
    assert page.split_by_words_calls == [[(0, 1)]]
    # Stub appended a new line containing the extracted word.
    assert len(page.lines_) == lines_before + 1
    assert page.lines_[-1].words[0].text == "world"
    # Source line lost the extracted word.
    assert len(page.lines_[0].words) == 1

    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    assert project_state.page_states[0].generation == gen_before + 1

    settings: Settings = loaded_client.app.state.settings  # type: ignore[attr-defined]
    assert cached_envelope_path(settings.cache_root, "book1", 0).exists()


# ── Coverage tests for the other 5 endpoints ─────────────────────────────


def test_copy_ocr_to_gt(loaded_client: TestClient) -> None:
    """POST /lines/{li}/copy-ocr-to-gt — ocr→gt for every word."""
    page = _make_two_line_page()
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/0/copy-ocr-to-gt",
        json={},
    )
    assert resp.status_code == 200, resp.text
    assert page.lines_[0].words[0].ground_truth_text == "hello"
    assert page.lines_[0].words[1].ground_truth_text == "world"
    # Line 1 untouched.
    assert page.lines_[1].words[0].ground_truth_text == ""
    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    assert project_state.page_states[0].generation == pstate.generation


def test_validate_line(loaded_client: TestClient) -> None:
    """POST /lines/{li}/validate — set Line.is_validated and propagate to words."""
    page = _make_two_line_page()
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/0/validate",
        json={"validated": True},
    )
    assert resp.status_code == 200, resp.text
    assert page.lines_[0].is_validated is True
    # Propagates to words (workaround for pd-book-tools#52 — same pattern
    # as words.py validate-batch).
    assert page.lines_[0].words[0].is_validated is True
    assert page.lines_[0].words[1].is_validated is True
    # Line 1 untouched.
    assert page.lines_[1].is_validated is False


def test_delete_line(loaded_client: TestClient) -> None:
    """POST /lines/{li}/delete — Page.delete_lines([li])."""
    page = _make_two_line_page()
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/0/delete",
        json={},
    )
    assert resp.status_code == 200, resp.text
    assert page.delete_lines_calls == [[0]]
    assert len(page.lines_) == 1


def test_split_after_word(loaded_client: TestClient) -> None:
    """POST /lines/{li}/split-after-word — Page.split_line_after_word(li, wi)."""
    page = _make_two_line_page()
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/0/split-after-word",
        json={"word_index": 0},
    )
    assert resp.status_code == 200, resp.text
    assert page.split_after_word_calls == [(0, 0)]
    # Stub split line 0 into two lines of 1 word each → 3 lines total.
    assert len(page.lines_) == 3


def test_refine_batch_returns_job_id(loaded_client: TestClient) -> None:
    """POST /lines/refine-batch — 202 with job_id; delegates to refine job.

    Spec §11: refine is a 202+job_id contract. The line-batch variant
    enqueues the existing refine job with scope=line + the requested
    line indices. No PageState seeding required — the refine job runs
    asynchronously and pulls the page itself.
    """
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/refine-batch",
        json={"line_indices": [0, 1], "mode": "refine", "padding_px": 2},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert "job_id" in body
    assert isinstance(body["job_id"], str) and body["job_id"]


# ── Error paths shared across the family ─────────────────────────────────


def test_copy_gt_to_ocr_returns_400_when_page_not_loaded(
    loaded_client: TestClient,
) -> None:
    """Without a seeded PageState, the handler returns 400 page_not_loaded."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/0/copy-gt-to-ocr",
        json={},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "page_not_loaded"


def test_merge_lines_rejects_single_index(loaded_client: TestClient) -> None:
    """merge with fewer than 2 indices → 400 mutation_failed.

    Page.merge_lines returns False on count < 2; the route surfaces that
    as mutation_failed (consistent with the spec-23-C2 contract).
    """
    page = _make_two_line_page()
    _seed_page_state(loaded_client, page_index=0, page=page)
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/merge",
        json={"line_indices": [0]},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "mutation_failed"


def test_split_after_word_404_for_bad_line(loaded_client: TestClient) -> None:
    """Bad line_index → 404 line_not_found before pd-book-tools call."""
    page = _make_two_line_page()
    _seed_page_state(loaded_client, page_index=0, page=page)
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/lines/99/split-after-word",
        json={"word_index": 0},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"] == "line_not_found"
