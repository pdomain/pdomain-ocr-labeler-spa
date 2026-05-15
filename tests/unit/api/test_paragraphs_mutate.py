"""Unit tests for paragraph-mutation endpoints (spec-23-D2, issue #318).

Spec authority:
- ``specs/23-page-payload-backend.md §9`` — paragraph-mutation endpoints
  (``copy-gt-to-ocr`` / ``copy-ocr-to-gt`` / ``validate`` / ``delete`` /
  ``merge`` / ``split-after-line``).
- ``specs/23-page-payload-backend.md §12-§13`` — autosave + per-page lock.
- ``specs/23-page-payload-backend.md §14`` — wire-shape stability for
  ``SplitParagraphAfterLineRequest`` (kept; D2 reuses the legacy schema).

Endpoints under test (6):

1. ``POST .../paragraphs/{pi}/copy-gt-to-ocr`` — ``Block.copy_ground_truth_to_ocr()``
   (Block is the paragraph type in pd-book-tools — same method used at
   line scope in spec-23-D1).
2. ``POST .../paragraphs/{pi}/copy-ocr-to-gt`` — ``Block.copy_ocr_to_ground_truth()``.
3. ``POST .../paragraphs/{pi}/validate`` — sets ``Block.is_validated`` on
   the paragraph and on every contained word (workaround for
   ConcaveTrillion/pd-book-tools#52 — same workaround as Word/Line).
4. ``POST .../paragraphs/{pi}/delete`` — ``Page.delete_paragraphs([pi])``
   (pd-book-tools exposes only the batch variant; matches the
   line-delete pattern).
5. ``POST .../paragraphs/merge`` — ``Page.merge_paragraphs(paragraph_indices)``.
6. ``POST .../paragraphs/{pi}/split-after-line`` — translates the
   within-paragraph ``after_line_index`` to a page-wide line index and
   calls ``Page.split_paragraph_after_line(page_line_index)``. Replaces
   the legacy stub; wire shape ``SplitParagraphAfterLineRequest`` kept.

Three contract tests required by the issue:
- copy-gt-to-ocr round-trip (paragraph words updated, gen bumped, cache).
- merge of two paragraphs (``Page.merge_paragraphs`` invoked with the
  two indices, gen bumped, cache written).
- split-after-line producing two paragraphs
  (``Page.split_paragraph_after_line`` invoked with the resolved
  page-wide line index, gen bumped, cache written).
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
        if self.ground_truth_text:
            self.text = self.ground_truth_text
            return True
        return False

    def copy_ocr_to_ground_truth(self) -> bool:
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


@dataclass
class _StubParagraph:
    """Mimics ``pd_book_tools.ocr.block.Block`` paragraph-level surface.

    Holds a list of ``_StubLine`` (matches Block.lines on a paragraph
    Block). copy_*/words mirror Block flat-list semantics.
    """

    line_objs: list[_StubLine] = field(default_factory=list)
    is_validated: bool = False

    @property
    def lines(self) -> list[_StubLine]:
        return self.line_objs

    @property
    def words(self) -> list[_StubWord]:
        return [w for ln in self.line_objs for w in ln.words]

    def copy_ground_truth_to_ocr(self) -> bool:
        results = [w.copy_ground_truth_to_ocr() for w in self.words]
        return any(results)

    def copy_ocr_to_ground_truth(self) -> bool:
        results = [w.copy_ocr_to_ground_truth() for w in self.words]
        return any(results)


@dataclass
class _StubPage:
    """Mimics ``pd_book_tools.ocr.page.Page`` paragraph-mutation surface."""

    paragraph_objs: list[_StubParagraph] = field(default_factory=list)
    label: str = "stub"

    # Recorded calls so tests can assert the route dispatched correctly.
    merge_paragraphs_calls: list[list[int]] = field(default_factory=list)
    delete_paragraphs_calls: list[list[int]] = field(default_factory=list)
    split_paragraph_after_line_calls: list[int] = field(default_factory=list)

    @property
    def paragraphs(self) -> list[_StubParagraph]:
        return self.paragraph_objs

    @property
    def lines(self) -> list[_StubLine]:
        return [ln for p in self.paragraph_objs for ln in p.line_objs]

    @property
    def words(self) -> list[_StubWord]:
        return [w for p in self.paragraph_objs for w in p.words]

    def merge_paragraphs(self, paragraph_indices: list[int]) -> bool:
        self.merge_paragraphs_calls.append(list(paragraph_indices))
        unique = sorted(set(paragraph_indices))
        if len(unique) < 2:
            return False
        for ix in unique:
            if not (0 <= ix < len(self.paragraph_objs)):
                return False
        keep_ix = unique[0]
        # Concatenate all lines from selected paragraphs into the first one;
        # drop the rest.
        merged_lines: list[_StubLine] = []
        for ix in unique:
            merged_lines.extend(self.paragraph_objs[ix].line_objs)
        new_paragraphs: list[_StubParagraph] = []
        for i, p in enumerate(self.paragraph_objs):
            if i == keep_ix:
                p.line_objs = merged_lines
                new_paragraphs.append(p)
            elif i in unique:
                continue
            else:
                new_paragraphs.append(p)
        self.paragraph_objs = new_paragraphs
        return True

    def delete_paragraphs(self, paragraph_indices: list[int]) -> bool:
        self.delete_paragraphs_calls.append(list(paragraph_indices))
        unique = sorted(set(paragraph_indices))
        if not unique:
            return False
        for ix in unique:
            if not (0 <= ix < len(self.paragraph_objs)):
                return False
        drop = set(unique)
        self.paragraph_objs = [p for i, p in enumerate(self.paragraph_objs) if i not in drop]
        return True

    def split_paragraph_after_line(self, line_index: int) -> bool:
        """Mirror pd-book-tools' Page.split_paragraph_after_line.

        ``line_index`` is the PAGE-WIDE index into ``page.lines``. We
        locate the containing paragraph by traversing the flat lines list
        and split that paragraph after ``after_offset`` (the within-
        paragraph offset of the target line).
        """
        self.split_paragraph_after_line_calls.append(line_index)
        flat_lines = self.lines
        if not (0 <= line_index < len(flat_lines)):
            return False
        target_line = flat_lines[line_index]
        # Find containing paragraph + within-paragraph offset.
        target_pi: int | None = None
        target_offset: int | None = None
        for pi, p in enumerate(self.paragraph_objs):
            if target_line in p.line_objs:
                target_pi = pi
                target_offset = p.line_objs.index(target_line)
                break
        if target_pi is None or target_offset is None:
            return False
        target_para = self.paragraph_objs[target_pi]
        if target_offset >= len(target_para.line_objs) - 1:
            # Can't split after the last line (matches pd-book-tools).
            return False
        first = target_para.line_objs[: target_offset + 1]
        second = target_para.line_objs[target_offset + 1 :]
        replacement = [
            _StubParagraph(line_objs=first),
            _StubParagraph(line_objs=second),
        ]
        self.paragraph_objs = (
            self.paragraph_objs[:target_pi] + replacement + self.paragraph_objs[target_pi + 1 :]
        )
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "lines": [{"words": [w.to_dict() for w in ln.words]} for ln in self.lines],
            "paragraphs": [],
            "words": [w.to_dict() for w in self.words],
            "source_identifier": f"{self.label}.png",
        }


def _make_word(text: str, gt: str = "") -> _StubWord:
    return _StubWord(text=text, ground_truth_text=gt)


def _make_line(*words: _StubWord) -> _StubLine:
    return _StubLine(words=list(words))


def _make_two_paragraph_page() -> _StubPage:
    """Two paragraphs x two lines x two words each."""
    p0 = _StubParagraph(
        line_objs=[
            _make_line(_make_word("alpha"), _make_word("beta")),
            _make_line(_make_word("gamma"), _make_word("delta")),
        ],
    )
    p1 = _StubParagraph(
        line_objs=[
            _make_line(_make_word("epsilon"), _make_word("zeta")),
            _make_line(_make_word("eta"), _make_word("theta")),
        ],
    )
    return _StubPage(paragraph_objs=[p0, p1], label="seeded")


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


def _seed_page_state(
    client: TestClient,
    *,
    page_index: int,
    page: _StubPage,
) -> PageState:
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


# ── 1. copy-gt-to-ocr (required contract test) ───────────────────────────


def test_paragraph_copy_gt_to_ocr_round_trip(loaded_client: TestClient) -> None:
    """POST /paragraphs/{pi}/copy-gt-to-ocr — gt→ocr for every word in paragraph.

    Asserts (spec §9 + §12 + §13):
    - 200 PagePayload response.
    - Every word in paragraph 0 has its ``text`` overwritten by ``ground_truth_text``.
    - Paragraph 1 is untouched.
    - ``pstate.generation`` advanced by exactly 1.
    - Cached envelope file written.
    """
    page = _make_two_paragraph_page()
    # Seed GT on every word in paragraph 0 (across both its lines).
    for li, line in enumerate(page.paragraph_objs[0].line_objs):
        for wi, word in enumerate(line.words):
            word.ground_truth_text = f"GT-{li}-{wi}"
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    gen_before = pstate.generation
    p1_original = [[w.text for w in ln.words] for ln in page.paragraph_objs[1].line_objs]

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/paragraphs/0/copy-gt-to-ocr",
        json={},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "book1"
    assert body["page_index"] == 0

    # Every word on paragraph 0 was rewritten.
    for li, line in enumerate(page.paragraph_objs[0].line_objs):
        for wi, word in enumerate(line.words):
            assert word.text == f"GT-{li}-{wi}"
    # Paragraph 1 untouched.
    assert [[w.text for w in ln.words] for ln in page.paragraph_objs[1].line_objs] == p1_original

    # Generation bumped exactly once.
    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    assert project_state.page_states[0].generation == gen_before + 1

    # Cached envelope written.
    settings: Settings = loaded_client.app.state.settings  # type: ignore[attr-defined]
    expected_cache = cached_envelope_path(settings.cache_root, "book1", 0)
    assert expected_cache.exists(), f"cached envelope not written: {expected_cache}"


# ── 2. merge two paragraphs (required contract test) ─────────────────────


def test_merge_two_paragraphs(loaded_client: TestClient) -> None:
    """POST /paragraphs/merge — call Page.merge_paragraphs with the two indices.

    Asserts:
    - 200 PagePayload response.
    - ``Page.merge_paragraphs`` called exactly once with ``[0, 1]``.
    - Resulting page has one paragraph containing all four original lines.
    - ``pstate.generation`` advanced by 1.
    - Cached envelope written.
    """
    page = _make_two_paragraph_page()
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    gen_before = pstate.generation

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/paragraphs/merge",
        json={"paragraph_indices": [0, 1]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "book1"

    assert page.merge_paragraphs_calls == [[0, 1]]
    assert len(page.paragraph_objs) == 1
    # The single remaining paragraph holds all four original lines (2 + 2).
    assert len(page.paragraph_objs[0].line_objs) == 4

    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    assert project_state.page_states[0].generation == gen_before + 1

    settings: Settings = loaded_client.app.state.settings  # type: ignore[attr-defined]
    assert cached_envelope_path(settings.cache_root, "book1", 0).exists()


# ── 3. split-after-line → two paragraphs (required contract test) ────────


def test_split_paragraph_after_line_produces_two_paragraphs(
    loaded_client: TestClient,
) -> None:
    """POST /paragraphs/{pi}/split-after-line — split a paragraph in two.

    Asserts (spec §9 — ``paragraph.split_after_line(l)`` → actual API
    ``Page.split_paragraph_after_line(page_line_index)``):
    - 200 PagePayload response.
    - pd-book-tools method invoked with the page-wide line index
      corresponding to (paragraph_index=0, after_line_index=0).
    - Resulting page has 3 paragraphs (split + untouched neighbor).
    - The split paragraph's two halves each carry the expected lines.
    - ``pstate.generation`` advanced by 1.
    - Cached envelope written.
    """
    page = _make_two_paragraph_page()  # 2 paragraphs x 2 lines each
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    gen_before = pstate.generation
    paragraphs_before = len(page.paragraph_objs)

    # Split paragraph 0 after its first line (within-paragraph index = 0).
    # The route must translate this to page-wide line index 0 because
    # paragraph 0 starts at the top of the page.
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/paragraphs/0/split-after-line",
        json={"paragraph_index": 0, "after_line_index": 0},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "book1"

    # pd-book-tools method invoked with page-wide line index = 0.
    assert page.split_paragraph_after_line_calls == [0]
    # Paragraph count grew by exactly one.
    assert len(page.paragraph_objs) == paragraphs_before + 1
    # New paragraphs at positions 0 and 1 are the two halves of original p0.
    assert len(page.paragraph_objs[0].line_objs) == 1
    assert len(page.paragraph_objs[1].line_objs) == 1
    # Original paragraph 1 still has its 2 lines and is now at index 2.
    assert len(page.paragraph_objs[2].line_objs) == 2

    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    assert project_state.page_states[0].generation == gen_before + 1

    settings: Settings = loaded_client.app.state.settings  # type: ignore[attr-defined]
    assert cached_envelope_path(settings.cache_root, "book1", 0).exists()


# ── Coverage tests for the other 3 endpoints ─────────────────────────────


def test_paragraph_copy_ocr_to_gt(loaded_client: TestClient) -> None:
    """POST /paragraphs/{pi}/copy-ocr-to-gt — ocr→gt for every word."""
    page = _make_two_paragraph_page()
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/paragraphs/0/copy-ocr-to-gt",
        json={},
    )
    assert resp.status_code == 200, resp.text
    # GT now mirrors OCR for every word in paragraph 0.
    assert page.paragraph_objs[0].line_objs[0].words[0].ground_truth_text == "alpha"
    assert page.paragraph_objs[0].line_objs[1].words[1].ground_truth_text == "delta"
    # Paragraph 1 untouched.
    assert page.paragraph_objs[1].line_objs[0].words[0].ground_truth_text == ""


def test_paragraph_validate(loaded_client: TestClient) -> None:
    """POST /paragraphs/{pi}/validate — set is_validated + propagate to words."""
    page = _make_two_paragraph_page()
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/paragraphs/0/validate",
        json={"validated": True},
    )
    assert resp.status_code == 200, resp.text
    assert page.paragraph_objs[0].is_validated is True
    # Workaround for pd-book-tools#52: propagate to every contained word.
    for line in page.paragraph_objs[0].line_objs:
        for word in line.words:
            assert word.is_validated is True
    # Paragraph 1 untouched.
    assert page.paragraph_objs[1].is_validated is False
    assert page.paragraph_objs[1].line_objs[0].words[0].is_validated is False


def test_paragraph_delete(loaded_client: TestClient) -> None:
    """POST /paragraphs/{pi}/delete — Page.delete_paragraphs([pi])."""
    page = _make_two_paragraph_page()
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/paragraphs/0/delete",
        json={},
    )
    assert resp.status_code == 200, resp.text
    assert page.delete_paragraphs_calls == [[0]]
    assert len(page.paragraph_objs) == 1


# ── Error paths ──────────────────────────────────────────────────────────


def test_paragraph_copy_gt_to_ocr_returns_400_when_page_not_loaded(
    loaded_client: TestClient,
) -> None:
    """Without a seeded PageState → 400 page_not_loaded."""
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/paragraphs/0/copy-gt-to-ocr",
        json={},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "page_not_loaded"


def test_paragraph_merge_rejects_single_index(loaded_client: TestClient) -> None:
    """merge with < 2 indices → 400 mutation_failed (mirrors lines/merge)."""
    page = _make_two_paragraph_page()
    _seed_page_state(loaded_client, page_index=0, page=page)
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/paragraphs/merge",
        json={"paragraph_indices": [0]},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "mutation_failed"


def test_paragraph_split_404_for_bad_paragraph(loaded_client: TestClient) -> None:
    """Bad paragraph_index → 404 paragraph_not_found before pd-book-tools call."""
    page = _make_two_paragraph_page()
    _seed_page_state(loaded_client, page_index=0, page=page)
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/paragraphs/99/split-after-line",
        json={"paragraph_index": 99, "after_line_index": 0},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"] == "paragraph_not_found"


def test_paragraph_split_400_when_after_line_out_of_paragraph(
    loaded_client: TestClient,
) -> None:
    """``after_line_index`` past the paragraph's last line → 400 mutation_failed.

    pd-book-tools' ``split_paragraph_after_line`` rejects splitting after
    the last line (and rejects out-of-range indices); we surface that as
    ``mutation_failed`` after the within-paragraph index has been
    translated to page-wide and dispatched.
    """
    page = _make_two_paragraph_page()
    _seed_page_state(loaded_client, page_index=0, page=page)
    # Paragraph 0 has 2 lines (indices 0, 1). Splitting after line 1
    # (the last line) is rejected by pd-book-tools.
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/paragraphs/0/split-after-line",
        json={"paragraph_index": 0, "after_line_index": 1},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "mutation_failed"
