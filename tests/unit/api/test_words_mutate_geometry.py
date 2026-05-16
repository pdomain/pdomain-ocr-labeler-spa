"""Unit tests for word geometry mutation endpoints (spec-23-C2, issue #316).

Spec authority:
- ``specs/23-page-payload-backend.md §9`` — word geometry endpoints (add,
  rebox, nudge, split, merge, erase-pixels): resolve target → call
  pd-book-tools mutation → bump generation → write cached envelope →
  return refreshed ``PagePayload``.
- ``specs/23-page-payload-backend.md §12`` — autosave + cached lane
  best-effort.
- ``specs/23-page-payload-backend.md §13`` — per-page locking.

pd-book-tools method audit (spec name → actual call):
- ``page.add_word(bbox, text, line_index=None)`` →
  ``Page.add_word_to_page(x1, y1, x2, y2, text)`` (closest-line picked
  automatically; ``line_index`` request field is informational only).
- ``word.rebox(bbox)`` → ``Page.rebox_word(li, wi, x1, y1, x2, y2)``.
- ``word.nudge(...)`` → ``Page.nudge_word_bbox(li, wi, left, right,
  top, bottom, refine_after)``.
- ``word.split(orientation, marker_position)`` →
  ``Page.split_word(li, wi, split_fraction)`` (horizontal only).
- ``page.merge_words(targets)`` — **missing** in pd-book-tools (tracking
  issue ConcaveTrillion/pd-book-tools#53); SPA route delegates to
  per-line ``Line.merge_word_left`` / ``Line.merge_word_right``.
- ``page.erase_pixels(bbox, fill_value)`` — **missing** in pd-book-tools
  (tracking issue #53); SPA handler mutates
  ``page.cv2_numpy_page_image`` in-place, mirroring the legacy labeler's
  inline implementation (``pd_ocr_labeler/state/page_state.py:1802``).

Three canonical happy-path tests (rebox, merge, erase-pixels per
issue #316) plus error-path coverage for the rest of the family.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
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


# ── Stub Page / Line / Word with geometry-mutation surface ───────────


@dataclass
class _StubWord:
    """Word stub recording mutations from rebox / nudge / split / merge calls."""

    text: str = "ocr"
    ground_truth_text: str = ""
    bounding_box: Any = None
    is_validated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "Word",
            "text": self.text,
            "ground_truth_text": self.ground_truth_text,
        }


@dataclass
class _StubLine:
    """Line stub with merge_word_left / merge_word_right surface.

    Each merge records the (word_index, direction) into ``merge_calls``
    and removes one neighbor — enough for the route to confirm it
    delegated correctly without dragging in pd-book-tools internals.
    """

    words_: list[_StubWord] = field(default_factory=list)
    merge_calls: list[tuple[int, str]] = field(default_factory=list)
    merge_should_succeed: bool = True

    @property
    def words(self) -> list[_StubWord]:
        return self.words_

    def merge_word_left(self, word_index: int) -> bool:
        self.merge_calls.append((word_index, "left"))
        if not self.merge_should_succeed:
            return False
        if word_index <= 0 or word_index >= len(self.words_):
            return False
        keep = self.words_[word_index - 1]
        keep.text = keep.text + self.words_[word_index].text
        del self.words_[word_index]
        return True

    def merge_word_right(self, word_index: int) -> bool:
        self.merge_calls.append((word_index, "right"))
        if not self.merge_should_succeed:
            return False
        if word_index < 0 or word_index >= len(self.words_) - 1:
            return False
        keep = self.words_[word_index]
        keep.text = keep.text + self.words_[word_index + 1].text
        del self.words_[word_index + 1]
        return True


@dataclass
class _StubPage:
    """Page-stub exposing the Page geometry-mutation surface.

    Records each call so handlers can be asserted against — and provides
    a real numpy ``cv2_numpy_page_image`` so erase-pixels has something
    to mutate.
    """

    lines_: list[_StubLine] = field(default_factory=list)
    label: str = "stub"
    cv2_numpy_page_image: Any = None
    rebox_calls: list[tuple[int, int, float, float, float, float]] = field(default_factory=list)
    add_calls: list[tuple[float, float, float, float, str]] = field(default_factory=list)
    nudge_calls: list[tuple[int, int, float, float, float, float, bool]] = field(default_factory=list)
    split_calls: list[tuple[int, int, float]] = field(default_factory=list)
    finalize_calls: int = 0
    rebox_should_succeed: bool = True
    add_should_succeed: bool = True
    nudge_should_succeed: bool = True
    split_should_succeed: bool = True

    @property
    def lines(self) -> list[_StubLine]:
        return self.lines_

    @property
    def paragraphs(self) -> list[_StubLine]:
        return self.lines_

    @property
    def words(self) -> list[_StubWord]:
        return [w for ln in self.lines_ for w in ln.words]

    def rebox_word(
        self,
        line_index: int,
        word_index: int,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        refine_after: bool = True,
    ) -> bool:
        self.rebox_calls.append((line_index, word_index, x1, y1, x2, y2))
        if not self.rebox_should_succeed:
            return False
        # Mirror real Page semantics: stash a tuple-shaped bbox onto the
        # target word so tests can assert the mutation took effect.
        if 0 <= line_index < len(self.lines_):
            line = self.lines_[line_index]
            if 0 <= word_index < len(line.words_):
                line.words_[word_index].bounding_box = (x1, y1, x2, y2)
        return True

    def add_word_to_page(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        text: str = "",
    ) -> bool:
        self.add_calls.append((x1, y1, x2, y2, text))
        if not self.add_should_succeed:
            return False
        # Add to first line (mirrors closest-line semantics for a single-line stub).
        if not self.lines_:
            return False
        self.lines_[0].words_.append(_StubWord(text=text, bounding_box=(x1, y1, x2, y2)))
        return True

    def nudge_word_bbox(
        self,
        line_index: int,
        word_index: int,
        left_delta: float,
        right_delta: float,
        top_delta: float,
        bottom_delta: float,
        refine_after: bool = True,
    ) -> bool:
        self.nudge_calls.append(
            (line_index, word_index, left_delta, right_delta, top_delta, bottom_delta, refine_after)
        )
        return self.nudge_should_succeed

    def split_word(
        self,
        line_index: int,
        word_index: int,
        split_fraction: float,
    ) -> bool:
        self.split_calls.append((line_index, word_index, split_fraction))
        return self.split_should_succeed

    def finalize_page_structure(self) -> None:
        self.finalize_calls += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "lines": [{"words": [w.to_dict() for w in ln.words]} for ln in self.lines_],
            "paragraphs": [],
            "words": [w.to_dict() for w in self.words],
            "source_identifier": f"{self.label}.png",
        }


def _make_seeded_page(*, with_image: bool = False) -> _StubPage:
    """Page with line 0 holding two words; optionally a 10x10 grey image."""
    page = _StubPage(
        lines_=[
            _StubLine(words_=[_StubWord(text="hello"), _StubWord(text="world")]),
        ],
        label="seeded",
    )
    if with_image:
        page.cv2_numpy_page_image = np.full((10, 10), 128, dtype=np.uint8)
    return page


# ── Loaded-project fixture ───────────────────────────────────────────


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


def _cached_envelope(client: TestClient, page_index: int) -> Path:
    settings: Settings = client.app.state.settings  # type: ignore[attr-defined]
    return cached_envelope_path(settings.cache_root, "book1", page_index)


# ── REBOX (mandatory per issue #316) ─────────────────────────────────


def test_rebox_word_calls_pdbooktools_and_writes_cached_envelope(
    loaded_client: TestClient,
) -> None:
    """POST /rebox: page.rebox_word called with converted (x1,y1,x2,y2),
    generation bumped, cached envelope written.
    """
    page = _make_seeded_page()
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    gen_before = pstate.generation

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/rebox",
        json={"bbox": {"x": 10, "y": 20, "width": 50, "height": 30}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == "book1"
    assert body["page_index"] == 0

    # Spec-23-C2: BBox(x, y, w, h) → (x1=x, y1=y, x2=x+w, y2=y+h).
    assert page.rebox_calls == [(0, 0, 10, 20, 60, 50)]
    # Mutation visible on the word.
    assert page.lines[0].words[0].bounding_box == (10, 20, 60, 50)

    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    assert project_state.page_states[0].generation == gen_before + 1
    assert _cached_envelope(loaded_client, 0).exists()


def test_rebox_word_returns_400_when_pdbooktools_rejects(
    loaded_client: TestClient,
) -> None:
    """If ``page.rebox_word`` returns False (invalid rect, etc.) the
    handler surfaces 400 ``mutation_failed`` — never silently no-ops.
    """
    page = _make_seeded_page()
    page.rebox_should_succeed = False
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/rebox",
        json={"bbox": {"x": 10, "y": 20, "width": 50, "height": 30}},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "mutation_failed"


def test_rebox_word_returns_404_for_bad_word_index(
    loaded_client: TestClient,
) -> None:
    page = _make_seeded_page()
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/99/rebox",
        json={"bbox": {"x": 1, "y": 1, "width": 2, "height": 2}},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"] == "word_not_found"


def test_rebox_word_returns_400_when_page_not_loaded(
    loaded_client: TestClient,
) -> None:
    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/rebox",
        json={"bbox": {"x": 1, "y": 1, "width": 2, "height": 2}},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "page_not_loaded"


# ── MERGE (mandatory per issue #316) ─────────────────────────────────


def test_merge_words_left_delegates_to_line_and_bumps_generation(
    loaded_client: TestClient,
) -> None:
    """POST /merge with direction=left calls line.merge_word_left,
    bumps generation, writes cached envelope.
    """
    page = _make_seeded_page()
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    gen_before = pstate.generation

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/1/merge",
        json={"direction": "left"},
    )
    assert resp.status_code == 200, resp.text

    assert page.lines[0].merge_calls == [(1, "left")]
    # Merge appended "world" onto "hello" → one word left, text="helloworld".
    assert len(page.lines[0].words) == 1
    assert page.lines[0].words[0].text == "helloworld"

    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    assert project_state.page_states[0].generation == gen_before + 1
    assert _cached_envelope(loaded_client, 0).exists()


def test_merge_words_right_delegates_to_line(loaded_client: TestClient) -> None:
    page = _make_seeded_page()
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/merge",
        json={"direction": "right"},
    )
    assert resp.status_code == 200, resp.text
    assert page.lines[0].merge_calls == [(0, "right")]
    assert page.lines[0].words[0].text == "helloworld"


def test_merge_words_returns_400_when_pdbooktools_rejects(
    loaded_client: TestClient,
) -> None:
    """e.g. cannot merge first word to the left — pd-book-tools returns False."""
    page = _make_seeded_page()
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/merge",
        json={"direction": "left"},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "mutation_failed"


# ── ERASE-PIXELS (mandatory per issue #316) ──────────────────────────


def test_erase_pixels_mutates_image_and_writes_cached_envelope(
    loaded_client: TestClient,
) -> None:
    """POST /erase-pixels: pixels inside bbox set to fill_value,
    generation bumped, cached envelope written.

    Mirrors legacy ``pd_ocr_labeler/state/page_state.py:1802``: clamps
    bbox to image extents and assigns ``image[top:bottom, left:right]
    = fill_value``.
    """
    page = _make_seeded_page(with_image=True)
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    gen_before = pstate.generation

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/erase-pixels",
        json={
            "bbox": {"x": 2, "y": 3, "width": 4, "height": 2},
            "fill_value": 255,
        },
    )
    assert resp.status_code == 200, resp.text

    img = page.cv2_numpy_page_image
    # Inside the rect: 255.
    assert int(img[3, 2]) == 255
    assert int(img[4, 5]) == 255
    # Outside the rect: original 128.
    assert int(img[0, 0]) == 128
    assert int(img[5, 6]) == 128
    # finalize_page_structure called after the mutation (mirrors legacy).
    assert page.finalize_calls == 1

    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    assert project_state.page_states[0].generation == gen_before + 1
    assert _cached_envelope(loaded_client, 0).exists()


def test_erase_pixels_clamps_to_image_bounds(loaded_client: TestClient) -> None:
    """Bbox extending past the image is clamped — no IndexError."""
    page = _make_seeded_page(with_image=True)
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/erase-pixels",
        json={
            "bbox": {"x": 8, "y": 8, "width": 20, "height": 20},
            "fill_value": 0,
        },
    )
    assert resp.status_code == 200, resp.text
    img = page.cv2_numpy_page_image
    assert int(img[8, 8]) == 0
    assert int(img[9, 9]) == 0


def test_erase_pixels_returns_400_when_no_image(loaded_client: TestClient) -> None:
    """Page without ``cv2_numpy_page_image`` → 400, not 500."""
    page = _make_seeded_page(with_image=False)
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/erase-pixels",
        json={"bbox": {"x": 1, "y": 1, "width": 2, "height": 2}, "fill_value": 0},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "mutation_failed"


def test_erase_pixels_circle_shape_spares_corners(loaded_client: TestClient) -> None:
    """``shape="circle"`` erases the inscribed ellipse but NOT the bbox corners.

    Verifies that brush ops (which send ``shape="circle"``) do not erase the
    corners of their bounding square — only the circular region the user
    actually painted.

    Setup: 20x20 white image (all 128).  Erase a 10x10 bbox centred at
    (5, 5) with ``fill_value=0`` and ``shape="circle"``.  The inscribed
    circle has centre (5, 5) radius 5.

    Assertions:
    - Centre pixel (5, 5) is erased (== 0).
    - Corners of the bbox (0,0), (9,0), (0,9), (9,9) are NOT erased (== 128).
    - A pixel just outside the circle but inside the bbox is NOT erased.
    """
    # Use a larger image so there's room for the 10x10 bbox.
    page = _make_seeded_page(with_image=False)
    page.cv2_numpy_page_image = np.full((20, 20), 128, dtype=np.uint8)
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/erase-pixels",
        json={
            "bbox": {"x": 0, "y": 0, "width": 10, "height": 10},
            "fill_value": 0,
            "shape": "circle",
        },
    )
    assert resp.status_code == 200, resp.text

    img = page.cv2_numpy_page_image
    # Centre of the circle (cx=5, cy=5 after // 2 → (0+10)//2=5) must be erased.
    assert int(img[5, 5]) == 0, "centre pixel must be erased"
    # Corners of the 10x10 bbox should NOT be erased — they are outside the
    # inscribed ellipse (radius ~5 from centre at [5,5]).
    # Corner (0,0): distance from centre is sqrt(25+25) ≈ 7.07 > 5 → not erased.
    assert int(img[0, 0]) == 128, "top-left corner must NOT be erased"
    assert int(img[0, 9]) == 128, "top-right corner must NOT be erased"
    assert int(img[9, 0]) == 128, "bottom-left corner must NOT be erased"
    assert int(img[9, 9]) == 128, "bottom-right corner must NOT be erased"
    # Pixels far outside the bbox must be untouched.
    assert int(img[15, 15]) == 128, "pixel outside bbox must be untouched"


def test_erase_pixels_rect_shape_fills_full_bbox(loaded_client: TestClient) -> None:
    """``shape="rect"`` (default) erases the full rectangle including corners."""
    page = _make_seeded_page(with_image=False)
    page.cv2_numpy_page_image = np.full((20, 20), 128, dtype=np.uint8)
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/erase-pixels",
        json={
            "bbox": {"x": 0, "y": 0, "width": 10, "height": 10},
            "fill_value": 0,
            "shape": "rect",
        },
    )
    assert resp.status_code == 200, resp.text

    img = page.cv2_numpy_page_image
    # Every pixel within the 10x10 bbox must be erased.
    assert int(img[0, 0]) == 0, "top-left corner must be erased (rect shape)"
    assert int(img[0, 9]) == 0, "top-right corner must be erased (rect shape)"
    assert int(img[9, 0]) == 0, "bottom-left corner must be erased (rect shape)"
    assert int(img[5, 5]) == 0, "centre must be erased (rect shape)"
    # Pixel just outside must be untouched.
    assert int(img[10, 10]) == 128, "pixel outside bbox must be untouched"


# ── ADD ──────────────────────────────────────────────────────────────


def test_add_word_calls_pdbooktools_and_bumps_generation(
    loaded_client: TestClient,
) -> None:
    page = _make_seeded_page()
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    gen_before = pstate.generation

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/add",
        json={
            "bbox": {"x": 5, "y": 5, "width": 20, "height": 10},
            "text": "new",
        },
    )
    assert resp.status_code == 200, resp.text

    assert page.add_calls == [(5, 5, 25, 15, "new")]
    assert len(page.lines[0].words) == 3
    assert page.lines[0].words[2].text == "new"

    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    assert project_state.page_states[0].generation == gen_before + 1
    assert _cached_envelope(loaded_client, 0).exists()


def test_add_word_returns_400_on_failure(loaded_client: TestClient) -> None:
    page = _make_seeded_page()
    page.add_should_succeed = False
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/add",
        json={"bbox": {"x": 1, "y": 1, "width": 2, "height": 2}, "text": ""},
    )
    assert resp.status_code == 400, resp.text


# ── NUDGE ────────────────────────────────────────────────────────────


def test_nudge_word_calls_pdbooktools_with_deltas(loaded_client: TestClient) -> None:
    page = _make_seeded_page()
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    gen_before = pstate.generation

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/nudge",
        json={"left": 1, "right": 2, "top": 3, "bottom": 4, "refine_after": True},
    )
    assert resp.status_code == 200, resp.text

    # Spec §9 row: nudge_word_bbox(li, wi, left, right, top, bottom, refine_after).
    assert page.nudge_calls == [(0, 0, 1, 2, 3, 4, True)]

    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    assert project_state.page_states[0].generation == gen_before + 1


# ── SPLIT ────────────────────────────────────────────────────────────


def test_split_word_horizontal_calls_pdbooktools(loaded_client: TestClient) -> None:
    page = _make_seeded_page()
    pstate = _seed_page_state(loaded_client, page_index=0, page=page)
    gen_before = pstate.generation

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/split",
        json={"x_fraction": 0.5, "direction": "horizontal"},
    )
    assert resp.status_code == 200, resp.text

    assert page.split_calls == [(0, 0, 0.5)]
    project_state = loaded_client.app.state.project_state  # type: ignore[attr-defined]
    assert project_state.page_states[0].generation == gen_before + 1


def test_split_word_vertical_returns_400(loaded_client: TestClient) -> None:
    """pd-book-tools only supports horizontal split today; vertical → 400."""
    page = _make_seeded_page()
    _seed_page_state(loaded_client, page_index=0, page=page)

    resp = loaded_client.post(
        "/api/projects/book1/pages/0/words/0/0/split",
        json={"x_fraction": 0.5, "direction": "vertical"},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"] == "mutation_failed"
    # And pd-book-tools was never called.
    assert page.split_calls == []
