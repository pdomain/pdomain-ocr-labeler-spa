# 18 — Text Normalization (Long-S, Ligatures, Glyph Variants)

How the SPA handles old-typesetting glyphs (`ſ`, `ﬁ`, `ﬂ`, `ﬃ`, `ﬄ`,
`ſt`-ligature, `ct`-ligature, ...) that diverge from the ASCII
ground-truth conventions used by PGDP and DocTR training corpora.

> Cross-refs:
> ADR — [`17-decisions.md`](17-decisions.md) D-025 (this is the
> source of truth; this spec elaborates).
> Implementation home — **pd-book-tools** (`pd_book_tools.text.normalize`)
> Toggle scope decided by [D-033](17-decisions.md) (project-level,
> persisted in `OCRConfig`); resolves Q-A2.

---

## 1. Principle

**OCR fidelity wins by default.** When DocTR (or any other engine)
produces `ſhall` for an old-typesetting page, that's what we store.
Modifying the OCR result in-place would lose information that may
matter for typography research, font fine-tuning, or
forensic-quality archival.

**PGDP fidelity wins on request.** When a downstream consumer needs
ASCII (Distributed Proofreaders, plain-text export), normalization
runs **on the way out** — not in the stored artefact.

**GT comparison can be normalization-aware** without modifying either
side. The matcher can know that `ſhall == shall` for fuzz-score
purposes while keeping `word.ocr_text = "ſhall"` and
`word.ground_truth_text = "shall"` distinct.

These three rules are the contract.

---

## 2. Where this lives

| Concern | Owner | Status |
|---|---|---|
| Glyph→ASCII map (long-s, ligatures, etc.) | `pd_book_tools.text.normalize` | NEW — added by pd-book-tools roadmap (delegated 2026-05-06) |
| Normalization-aware fuzz matcher | `pd_book_tools.ocr.ground_truth_matching` | EXTEND |
| Output-time normalization (plaintext) | `pd_book_tools.text.normalize.normalize_string(...)` | NEW |
| `--normalize-output {none\|ascii}` flag | `pd-ocr-cli` (delegated 2026-05-06) | ROADMAP |
| Per-package normalize-on-export | `pd-prep-for-pgdp` | ROADMAP (no agent yet — flag for future delegation) |
| **Toggle in the labeler** | `pd-ocr-labeler-spa` | THIS SPEC, M9 polish |

The SPA itself ships **no** glyph map. It calls into pd-book-tools.
If pd-book-tools hasn't shipped the API yet, the toggle is hidden /
disabled with a "feature not yet available" tooltip.

---

## 3. The glyph map (lives in pd-book-tools)

Canonical mapping:

| Glyph | ASCII | Notes |
|---|---|---|
| `ſ` (U+017F LATIN SMALL LETTER LONG S) | `s` | The classic long-s; common in pre-1800s typesetting |
| `ﬁ` (U+FB01) | `fi` | Latin small ligature fi |
| `ﬂ` (U+FB02) | `fl` | Latin small ligature fl |
| `ﬃ` (U+FB03) | `ffi` | |
| `ﬄ` (U+FB04) | `ffl` | |
| `ﬅ` (U+FB05) | `st` | Long-s + t |
| `ﬆ` (U+FB06) | `st` | s + t |
| `Œ` / `œ` (U+0152/0153) | `OE` / `oe` | French/Latin |
| `Æ` / `æ` (U+00C6/00E6) | `AE` / `ae` | (debatable — often kept) |

The map is **conservative**: it covers glyphs whose ASCII expansion
is unambiguous. Greek diacritics, accented Latin (é, ñ, ü), and
similar are NOT in the default map; they require locale-specific
profiles. v1 ships only the `ascii` profile (the table above).

Future profiles may include `gaelic` (Cló Gaelach long-i, etc.),
`fraktur` (specific German typeset choices), `greek-polytonic`
(diacritics → monotonic).

---

## 4. Normalization-aware fuzz matching

Today's fuzz match (`pd_book_tools.ocr.ground_truth_matching`) compares
`word.ocr_text` against `word.ground_truth_text` byte-for-byte (or with
a fuzz-distance algorithm). When the OCR returns `ſhall` and the GT
says `shall`, the current behaviour:

- exact: false
- fuzz_score: ~0.83 (one substitution out of 6)
- match_status: `fuzzy`

Proposed normalization-aware behaviour (opt-in):

- Compare `normalize_string(ocr_text)` vs `normalize_string(gt_text)`.
- If equal → `match_status = exact`, `fuzz_score = 1.0`, BUT preserve
  both raw strings on the `WordMatch`.
- If not equal → fall back to fuzz on the original strings.

The `WordMatch` model gains an optional `normalized_match: bool` that
indicates "exact only after normalization". The SPA can render a
small badge on such matches to make the normalization visible.

The matcher is enabled per-call via a flag, defaulting to **off**.
Callers (pd-ocr-labeler-spa, pd-prep-for-pgdp) opt in.

---

## 5. Output-time normalization

Two output paths in the SPA care:

### 5.1 Plain-text page export

`PagePayload.page_text_ocr` and `page_text_gt` are strings used by
the read-only OCR / GT tabs in the matches view (see
[`05-word-matches.md`](05-word-matches.md) §1).

By default these contain raw OCR (with glyphs). The OCR config can
toggle "Render normalized in plaintext tabs" — when on, the SPA calls
`pd_book_tools.text.normalize.normalize_string(s, profile="ascii")`
before sending. The Matches view (per-word) is unaffected.

### 5.2 DocTR export

Already covered by [`10-export.md`](10-export.md). The export request
gains a `normalize_recognition_labels: bool = false` flag. When true,
the recognition `labels.json` strings are normalized before write.

The cached training images themselves are unchanged (image bytes are
the OCR target). Only the *label* strings change.

---

## 6. SPA toggle UI

(M9 polish — not in M0–M8.)

Location: OCR config modal (`<OCRConfigModal />`), new section "Text
normalization":

```
☐ Use normalization-aware GT matching (treat ſhall as matching shall)
☐ Normalize plaintext tabs (Page OCR / GT tabs render ASCII)
[Profile ▼] ascii  (greyed out — only profile in v1)
```

When pd-book-tools `pd_book_tools.text.normalize` is unavailable
(import fails / older pin), the section shows a "Requires pd-book-tools
≥ X.Y.Z" hint and the toggles are disabled.

testids:
- `normalize-gt-matching-checkbox`
- `normalize-plaintext-checkbox`
- `normalize-profile-select`

---

## 7. Migration / compat with legacy

The legacy `pd-ocr-labeler` does no normalization. Its
`payload.page_text_ocr` (when serialised) contains raw OCR. The SPA
preserves this on read; if the user enables a plaintext-tab
normalization toggle in v9, the DISPLAY changes but the saved
envelope is unchanged.

Driver-agent compatibility ([`13-driver-contract.md`](13-driver-contract.md)):
the new testids are additive. Driver tests pass.

---

## 8. Persistence

`OCRConfig` (the on-disk YAML config) gains two optional fields:

```yaml
# config.yaml
source_projects_root: "/path/to/projects"
normalize_for_gt_matching: false
normalize_plaintext_tabs: false
normalize_profile: "ascii"
```

Defaults match legacy behaviour (everything off). Schema bump on
config: trivial — `extra="ignore"` covers it; no version field on
config.yaml today.

---

## 9. Tests

- Unit: `test_normalize_string.py` (in pd-book-tools, when added) —
  table-driven over the glyph map.
- Unit: `test_match_with_normalization.py` (in pd-book-tools) — fuzz
  comparison with toggle on/off.
- Backend: `test_ocr_config_normalize.py` — toggle persists, applied
  to plaintext tabs when on.
- E2E: `test_normalization_toggle.py` (M9) — open OCR config, enable
  GT matching, verify a `ſhall`/`shall` cell shows `exact` instead of
  `fuzzy`.

---

## 10. Open issues

- **Q-A2** (toggle scope). Listed in [`OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md).
  Spec author bet: project-level (in OCR config). User to confirm.
- **Profile registry**. v1 ships `ascii` only. Future profiles
  (`gaelic`, `fraktur`, `greek`) need a clean registry pattern in
  pd-book-tools — out of scope here.
- **Round-trip determinism**. `normalize_string("ſhall") = "shall"` ✓.
  But `normalize_string("shall") = "shall"` (idempotent). The map
  must be one-way — we never *un*-normalize. Document this in
  pd-book-tools.
- **Diacritics interaction with `PGDPResults`**.
  `pd_book_tools.pgdp.pgdp_results.PGDPResults` already does some
  diacritic processing for GT. We must NOT double-normalize: if GT
  is `[oe]` → `oe` (PGDP markup) and `oe` is then normalized to
  itself, fine. If OCR is `œ`, comparing normalize(`œ`) = `oe`
  matches GT `oe`. Test golden files needed.
