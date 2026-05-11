# 19 — Auto-Rotation + Manual Rotate

> **Status**: Active
> **Last updated**: 2026-05-11
> **Spec-Issue**: ConcaveTrillion/pd-ocr-labeler-spa#42

Pages from book scans sometimes arrive rotated (sideways, upside-down).
The SPA must detect, optionally auto-correct, and always allow manual
correction.

> Cross-refs:
> ADR — [`17-decisions.md`](17-decisions.md) D-029 (source of truth)
> Open sub-questions — [`OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md)
> Q-A1 (envelope schema bump), Q-A3 (indicator UI placement)
> Page actions — [`08-page-actions.md`](08-page-actions.md)
> Driver contract — [`13-driver-contract.md`](13-driver-contract.md)

---

## 1. Two surfaces

### 1.1 Manual rotate (always available, ships in M9)

Two buttons in `<PageActions />`:

| Button | testid | Action |
|---|---|---|
| Rotate ↺ (CCW) | `rotate-ccw-button` | POST `.../rotate {degrees: -90}` |
| Rotate ↻ (CW) | `rotate-cw-button` | POST `.../rotate {degrees: 90}` |

Optional: a 180° button (`rotate-180-button`) for upside-down pages.

The endpoint:

```
POST /api/projects/{project_id}/pages/{page_index}/rotate
Body: { "degrees": -90 | 90 | 180, "manual": true }
Returns: PagePayload
```

Backend behaviour:

- Rotate the in-memory page image by `degrees` (CCW positive in
  numpy / OpenCV convention; CW positive in PIL — be explicit:
  CW positive on the wire).
- Re-run OCR on the rotated image (fresh predictor call). This is
  the only way the bboxes update sensibly.
- Update `PageRecord.rotation_degrees = (rotation_degrees + degrees) % 360`.
- Auto-save to cache.
- Return updated `PagePayload`.

Manual rotate is **slow** (re-runs OCR). Returns a Job (202
Accepted) like Reload OCR — see [`08-page-actions.md`](08-page-actions.md) §2.

### 1.2 Auto-rotate (project-load pass, ships post-M9)

When a project loads, an opt-in pre-pass evaluates every page's
correct rotation and applies it before the first OCR.

| Setting | Default | Where |
|---|---|---|
| `auto_rotate_on_load` | true | OCR config modal new section "Auto-rotation" |
| `auto_rotate_method` | `"gt-best-match"` if GT present, else `"layout"` | Same |

Algorithm (see §3 below): try 0/90/180/270, pick the rotation whose
OCR best matches the GT (or when no GT, whose layout-analysis
score is highest).

The auto-rotate result is treated as the page's "natural" rotation;
manual rotate buttons stack on top.

`PageRecord` field:

```python
class PageRecord(BaseModel):
    ...
    rotation_degrees: int = 0           # canonical rotation applied
    rotation_source: Literal["none", "auto", "manual"] = "none"
```

---

## 2. Rotation indicator UI

(Q-A3 lists three options; spec author bet is **B** — separate badge.)

Layout in `<PageActions />`:

```
... [Page name]   [LABELED]   [↻ 90 auto]
```

- testid: `rotation-badge` (always present; hidden via CSS when
  `rotation_degrees == 0`).
- Tooltip: "Auto-rotated 90° clockwise. Click to revert." (Click =
  POST `.../rotate {degrees: -<rotation_degrees>, manual: true}`).
- Color: gray (auto), blue (manual).

Tooltip text variants:

- `rotation_source == "auto"` → "Auto-rotated 90° clockwise. Click to revert."
- `rotation_source == "manual"` → "Manually rotated 90° clockwise."
- `rotation_source == "none"` → (badge hidden)

---

## 3. GT-best-match rotation algorithm

When GT exists for a page and the user has `auto_rotate_method =
"gt-best-match"`, the algorithm is:

```python
def find_best_rotation(image_bytes, gt_text, ocr_engine) -> tuple[int, float]:
    """Returns (rotation_degrees, confidence).

    rotation_degrees ∈ {0, 90, 180, 270}.
    confidence ∈ [0, 1].
    """
    candidates = [0, 90, 180, 270]
    scores = []
    for deg in candidates:
        rotated = rotate_image(image_bytes, deg)
        ocr_text = ocr_engine.ocr_image(rotated, fast=True).text  # detection-only
        score = fuzz.ratio(normalize(ocr_text), normalize(gt_text)) / 100.0
        scores.append(score)
    best_idx = max(range(4), key=lambda i: scores[i])
    return candidates[best_idx], scores[best_idx]
```

Implementation lives in `pd_book_tools.ocr.rotation` (new module —
flag for delegation to pd-book-tools agent if not already in their
roadmap).

The `fast=True` flag on `ocr_engine.ocr_image` is a hint to use a
detection-only path that's ~10x faster than full recognition. The
score doesn't need full word-level accuracy; line-count + character-
density signals are enough.

When **no GT** is present, fall back to `"layout"` method:

```python
def find_best_rotation_layout(image_bytes, layout_engine) -> tuple[int, float]:
    """Pick the rotation with the highest layout-analysis confidence
    (lines detected, paragraphs detected, average column-aspect ratio
    matches typical book pages).
    """
    ...
```

Layout method lives in pd-book-tools (it already runs layout analysis
during OCR; rotation can piggy-back).

---

## 4. Backend endpoints

### `POST /api/projects/{id}/pages/{idx}/rotate`

Synchronous if `degrees` is a multiple of 90 (cheap); 202 + Job if
rotation triggers a Reload OCR (always, in v1, because bboxes change).

```python
class RotatePageRequest(BaseModel):
    degrees: Literal[-180, -90, 90, 180]
    manual: bool = True
    rerun_ocr: bool = True
```

### `POST /api/projects/{id}/auto-rotate-all`

(Future, M9.x or later.) Iterates every page, applies the best-match
algorithm, returns a `Job`.

```python
class AutoRotateAllRequest(BaseModel):
    method: Literal["gt-best-match", "layout"] | None = None  # None = "auto-pick"
    overwrite_manual: bool = False  # if true, overrides manual rotations
```

---

## 5. Persistence

The user's question Q-A1 surfaces here: where does
`rotation_degrees` live in the envelope?

**Recommendation:** v2.2 envelope (additive bump):

```jsonc
{
  "schema": {"name": "pd_ocr_labeler.user_page", "version": "2.2"},
  ...
  "source": {
    ...
    "rotation_degrees": 0,
    "rotation_source": "auto" | "manual" | "none"
  },
  ...
}
```

Verify legacy v2.1 reader behaviour first:

- Legacy uses `extra="ignore"` (or equivalent) on the nested provenance
  blocks but `extra="forbid"` on the schema field check. **Test:** open
  a v2.2 envelope in legacy. If it crashes, ship Q-A1 option **(B)**
  (sidecar file) instead.

If legacy can read v2.2 (ignoring extra fields), bump to 2.2 in M9.

---

## 6. Driver-contract additions

New testids (additive):

| testid | Element |
|---|---|
| `rotate-ccw-button` | Rotate ↺ button in PageActions |
| `rotate-cw-button` | Rotate ↻ button in PageActions |
| `rotate-180-button` | Rotate 180° button (optional) |
| `rotation-badge` | Rotation indicator badge |
| `auto-rotate-checkbox` | OCR config: enable auto-rotate on load |
| `auto-rotate-method-select` | OCR config: method dropdown (gt-best-match / layout) |

URL invariants unchanged.

---

## 7. Milestone placement

Auto-rotation is a **post-GA enhancement**:

- Manual rotate buttons (M9.1): cheap, useful, doesn't risk
  destabilising M0–M8.
- Auto-rotation pass (M9.2 or M10): heavier; depends on
  pd-book-tools `rotation` module being available.

Add as a new milestone in [`16-milestones.md`](16-milestones.md):

> ### M9.1 — Manual rotation
>
> Outcome: rotate-CW/CCW buttons in PageActions. POST
> .../rotate triggers Reload OCR. Source badge shows rotation.
>
> ### M9.2 — Auto-rotation
>
> Outcome: project-load pass detects rotation per page; configurable
> method (gt-best-match / layout). Indicator badge distinguishes
> auto vs manual.

---

## 8. Tests

- Backend: `test_rotate_endpoint.py` — POST .../rotate {degrees:90};
  page image is rotated; bboxes are recomputed; envelope persists.
- Backend: `test_rotation_idempotent.py` — rotate +90 four times;
  result equals original.
- Backend: `test_gt_best_match_rotation.py` — fixture with a sideways
  scan; algorithm picks 90° as the answer (golden).
- E2E: `test_manual_rotate.py` — click rotate-CW; image visibly
  rotates; matches view re-renders with new bboxes.
- E2E: `test_auto_rotate_indicator.py` — load fixture with sideways
  page; badge shows "↻ 90 auto"; click revert; badge hides.

---

## 9. Open issues

- **Q-A1** (envelope schema bump). Listed in [`OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md).
- **Q-A3** (indicator UI placement). Same.
- **Performance.** Auto-rotating a 200-page book on first load is
  slow (~4× detection-only OCR per page = ~5 minutes). Show a
  cancel-able job. The first-page-OCR result is cached, so
  re-loading the project re-uses the cached rotation.
- **GT absence.** When GT is missing entirely (most projects in
  practice), the layout-method fallback runs. We need pd-book-tools
  to expose a `layout_only_orientation_score(image)` function. Flag
  for delegation to pd-book-tools agent in a follow-up.
- **Tilt vs cardinal rotation.** This spec covers 90° increments
  only. Skew correction (e.g. 3° tilt) is a separate concern and
  out of scope for v1.
