# Conformance Fixtures — UserPageEnvelope v2.1

Frozen `UserPageEnvelope` v2.1 JSON files used by
`tests/conformance/test_legacy_envelopes.py` to guard backward-compatibility.

## What these fixtures represent

Each file is a per-page envelope in the format that the legacy
`pd-ocr-labeler` writes. The SPA must be able to round-trip
(parse → rebuild) every fixture here without data loss. Any failure
means v2.1 compat is broken.

## Provenance

| File | Source | Notes |
|------|--------|-------|
| `browser-test-project_001.json` | Derived from `pd-ocr-labeler` browser-test-project | Page 1; v2.1; copied from `tests/fixtures/envelopes/` |
| `browser-test-project_002.json` | Derived from `pd-ocr-labeler` browser-test-project | Page 2; v2.1 |
| `browser-test-project_003.json` | Derived from `pd-ocr-labeler` browser-test-project | Page 3; v2.1 |

## How to add a new fixture

1. Export an envelope from a running labeler session (save a page in
   `pd-ocr-labeler` or `pdomain-ocr-labeler-spa`, copy the `_NNN.json` file).
2. Place it in this directory as `<project>_<NNN>.json`.
3. Add a row to the provenance table above.
4. Run `just test` — the new fixture is picked up automatically by the
   parametrised test.
