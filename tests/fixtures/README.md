# Test Fixtures

This directory contains shared test fixtures used by the pdomain-ocr-labeler-spa
test suite.

## Structure

```
tests/fixtures/
├── envelopes/          # UserPageEnvelope v2.1 JSON files (golden fixtures)
│   ├── browser-test-project_001.json
│   ├── browser-test-project_002.json
│   └── browser-test-project_003.json
└── README.md           # this file
```

## `envelopes/` — UserPageEnvelope v2.1 fixtures

Per-page envelopes in v2.1 format. Used by:

- `tests/integration/test_envelope_round_trip.py` — dict-equal round-trip.
- `tests/conformance/test_legacy_envelopes.py` — conformance guard (same fixtures
  mirrored in `tests/conformance/fixtures/`).

### Provenance

Derived from the `browser-test-project` test project. These envelopes represent
pages that the legacy `pd-ocr-labeler` would have written in v2.1 format.

### Adding new fixtures

1. Export a per-page envelope from `pd-ocr-labeler` or `pdomain-ocr-labeler-spa`
   (the `<project>_NNN.json` sidecar in the project's `page-images/` directory).
2. Drop it here as `<project>_NNN.json`.
3. Run `just test` — the parametrised tests pick it up automatically.
4. Also copy to `tests/conformance/fixtures/` and update that README.
