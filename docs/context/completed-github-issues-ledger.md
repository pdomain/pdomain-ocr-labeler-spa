---
kind: context
status: active
owner: maintainers
created: 2026-07-19
last_verified: 2026-07-19
---

# Completed GitHub issues migration ledger

## Agent Index

- **Kind:** context
- **Status:** active
- **Owner:** maintainers
- **Last verified:** 2026-07-19
- **Read when:** reconciling completed GitHub issues with durable repository documentation.
- **Search terms:** GitHub issue migration, completed issues, raw digest, deletion status, architecture coverage.

## Coverage ledger

Each row maps one closed GitHub issue to a durable record. A row becomes
deletion-ready only after an independent review verifies its raw digest,
outcome, evidence, and destination on the remote default branch.

| Issue | Raw SHA-256 | Outcome | Durable destination and evidence | Deletion status |
| --- | --- | --- | --- | --- |
| [#448](https://github.com/pdomain/pdomain-ocr-labeler-spa/issues/448) | `28a0e68d009ebdc0187ea20295797868be0afff00096948bd7221d1d35000af6` | Implemented | `docs/specs/behavior/screen-root.md` B-ROOT-002; `RootPage.test.tsx`; commit `e1bbe1f` | Awaiting merged cutover |
| [#449](https://github.com/pdomain/pdomain-ocr-labeler-spa/issues/449) | `8203c3c813882c7e8909a5142a74d8dcfb331e38da394469cdc1f83e8a71db6d` | Implemented; architecture corrected | `docs/architecture/03-frontend.md`; `client.test.ts`; commit `9ac12ba` | Awaiting merged cutover |
| [#450](https://github.com/pdomain/pdomain-ocr-labeler-spa/issues/450) | `f5dc736d6959d72cf1bf748afda2b58f2b9ef3aa9adb5df72a9b982adc87a305` | Implemented; architecture promoted | `docs/architecture/28-palettes-pickers.md`; `Chip.test.tsx`; commits `caba908`, `fcab138` | Awaiting merged cutover |
| [#451](https://github.com/pdomain/pdomain-ocr-labeler-spa/issues/451) | `a2a35c287ddbe722f5fca87ba69f4a264e04808bbf2d703452dc6e7ba2b72d0c` | Implemented | `docs/architecture/13-driver-contract.md`; `test_driver_contract.py`; commit `3b09ac8` | Awaiting merged cutover |
| [#452](https://github.com/pdomain/pdomain-ocr-labeler-spa/issues/452) | `1508ff64c01ef35fa9155e5d0887442cc8f0ff410ed3ed9de7df7915bb7f5585` | Implemented | `docs/architecture/06-toolbar-actions.md`; `ToolbarActionGrid.test.tsx`; commit `2f1788d` | Awaiting merged cutover |
| [#453](https://github.com/pdomain/pdomain-ocr-labeler-spa/issues/453) | `17d09f00710e422879fa75eb6faf628835a55244bc438ecb8aa84f730a40c9ac` | Implemented | `docs/architecture/13-driver-contract.md` section 2.8; `tests/e2e/test_driver_contract.py`; commit `c9ce0e8` | Awaiting merged cutover |
| [#454](https://github.com/pdomain/pdomain-ocr-labeler-spa/issues/454) | `29141e7918067994c5da74410fe58b80f598c79810ddaf897e0555a810fb1c58` | Historical fix implemented; standalone dialog later superseded | `docs/architecture/13-driver-contract.md` still conflicts with `docs/context/intent-map.md` and current code | Not deletion-ready: reconcile driver contract and tests |
| [#455](https://github.com/pdomain/pdomain-ocr-labeler-spa/issues/455) | `aba820561d7c468892889a7682fc29ce438b09e57c5ef14d1dfd49ce5fa6dd47` | Implemented | `docs/architecture/13-driver-contract.md`; route integration tests; commit `c4a11c8` | Awaiting merged cutover |
| [#456](https://github.com/pdomain/pdomain-ocr-labeler-spa/issues/456) | `c79bd1a408f10bb8046b9c582de6e57ec8aa259621a44e9e1c580e2055ebbb0b` | Partial: global ignore removed; policy contradiction remains | `docs/context/intent-map.md`; `pyproject.toml`; `CONVENTIONS.md`; commit `c754f35` | Not deletion-ready: owner decision required |
| [#459](https://github.com/pdomain/pdomain-ocr-labeler-spa/issues/459) | `315a95cb1dd7f848aa4ae224f30856e9ed2fe3a33f1e25d0f645721e36d6e25a` | Implemented, then evolved | `docs/context/decisions.md`; current resolvers in `api/words.py` and `api/pages.py`; commit `b66fc19` | Awaiting merged cutover |

## Batch verification

- The export contained 429 issues at batch start: 425 closed and 4 open.
- The migration workspace stores raw records in
  `/tmp/pdomain-ocr-labeler-spa-issue-migration-20260719/raw/`. The table stores
  their immutable digests.
- Coverage review: independent adversarial review completed on 2026-07-19.
- Cutover commit: not yet merged.
- GitHub deletion: not started.
