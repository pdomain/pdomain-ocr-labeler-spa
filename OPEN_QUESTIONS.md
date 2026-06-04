# Open Questions for `pdomain-ocr-labeler-spa`

> **Resolved questions are archived in [`docs/archive/research/QUESTIONS_RESOLVED.md`](docs/archive/research/QUESTIONS_RESOLVED.md).**
> Only currently-open questions live below. When a question is answered, move
> its full entry to the archive in the same commit that lands the resolution
> ADR (see [`docs/process/DEVELOPMENT.md` § Archive on close](docs/process/DEVELOPMENT.md#archive-on-close)).

Questions the spec authors could not resolve from the source material alone.
Each entry: **Q** (the question), **Context** (why it matters), **Options**
(with trade-offs), **Recommendation** (spec author's bet), **Blocks** (which
milestones can't start until resolved). Once the user answers, a **Resolution**
line links the resulting ADR and the entry moves to the archive.

---

## Open questions

### Q-B2-STYLE-LABELS: toolbar style/component labels don't match book-tools

**Q:** The toolbar Apply-Style row in `frontend/src/components/ToolbarActionGrid.tsx`
hardcodes `TEXT_STYLE_LABELS` and `WORD_COMPONENT_LABELS` that diverge from
the canonical book-tools vocabulary. Notably the grid offers `"italic"`
(singular) but `normalize_text_style_label` only accepts `"italics"` (plural);
applying `"italic"` raises `ValueError` → HTTP 500. The full allowed set is:
`all caps, blackletter, bold, handwritten, italics, monospace, regular,
small caps, strikethrough, underline`.

**Context:** Lane B / B2 wired the Apply-Style / Component controls to the real
`words/{li}/{wi}/style` + `.../component` routes. The wiring is correct, but
the grid's hardcoded option values will 500 the backend for any mismatched
label (at minimum `italic`). The B3 integration test uses the valid `"italics"`
to prove the route works. The frontend unit test mocks the backend so it does
not catch the mismatch.

**Options:**

- (a) Hardcode the corrected canonical labels in the grid (quick, but still a
  duplicated vocabulary that can drift again).
- (b) Source the allowed labels from the backend (a new
  `GET /api/text-style-labels` or extend `/api/ocr-config`), so the grid never
  drifts — fits the Lane C OCR-config work.

**Recommendation:** (b) longer-term; (a) as a stopgap if a fix is needed before
Lane C. Either way the label list belongs to a follow-up, not Lane B's wireup.

**Blocks:** nothing hard — the grid is in a hidden stub today. Surfacing it
(Lane C / D) should resolve this first so the visible control can't 500.
