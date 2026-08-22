from __future__ import annotations

import hashlib
import json
import os
import signal
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path

import pytest
from pdomain_book_tools.typography import (
    GRAPHEME_SEGMENTATION_VERSION,
    TypographyCorrection,
)

from pdomain_ocr_labeler_spa.core.typography_review import (
    ImportedTextBinding,
    ImportedTextValidationLog,
    StaleImportedTextValidationError,
    StaleTypographyBindingError,
    TypographyBinding,
    TypographyCorrectionLog,
    stable_page_id,
    stable_word_id,
)


def test_imported_text_validation_is_persistent_and_cas_bound(tmp_path: Path) -> None:
    log = ImportedTextValidationLog(tmp_path, corpus_root=tmp_path)
    binding = ImportedTextBinding(
        bundle_id="a" * 64,
        page_id="pgdp:alpha:001.png",
        page_sha256="b" * 64,
        page_head_sha256="c" * 64,
        word_id="word-1",
        text="Exact text",
        text_sha256=hashlib.sha256(b"Exact text").hexdigest(),
    )
    head = log.head(binding)
    assert head.validated is False

    saved = log.append(binding, validated=True, expected_head=head.head_token)

    assert ImportedTextValidationLog(tmp_path, corpus_root=tmp_path).head(binding) == saved
    with pytest.raises(StaleImportedTextValidationError):
        log.append(binding, validated=False, expected_head=head.head_token)


def test_imported_text_validation_does_not_resurrect_across_a_b_a(tmp_path: Path) -> None:
    log = ImportedTextValidationLog(tmp_path, corpus_root=tmp_path)

    def binding(bundle: str, text: str) -> ImportedTextBinding:
        return ImportedTextBinding(
            bundle_id=bundle * 64,
            page_id="pgdp:alpha:001.png",
            page_sha256=hashlib.sha256(text.encode()).hexdigest(),
            page_head_sha256=hashlib.sha256(f"head:{text}".encode()).hexdigest(),
            word_id="word-1",
            text=text,
            text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        )

    first_a = binding("a", "A")
    log.append(first_a, validated=True, expected_head=log.head(first_a).head_token)
    assert log.head(first_a).validated is True
    assert log.head(binding("b", "B")).validated is False
    assert log.head(first_a).validated is False


def test_imported_text_validation_recovers_truncated_tail_and_rejects_symlink(
    tmp_path: Path,
) -> None:
    binding = ImportedTextBinding(
        bundle_id="a" * 64,
        page_id="pgdp:alpha:001.png",
        page_sha256="b" * 64,
        page_head_sha256="c" * 64,
        word_id="word-1",
        text="Exact text",
        text_sha256=hashlib.sha256(b"Exact text").hexdigest(),
    )
    log = ImportedTextValidationLog(tmp_path, corpus_root=tmp_path)
    log.head(binding)
    with log.path.open("ab") as stream:
        stream.write(b'{"truncated"')
    log.append(binding, validated=True, expected_head=log.head(binding).head_token)
    assert log.head(binding).validated is True

    other = tmp_path / "other"
    other.write_text("")
    log.path.unlink()
    log.path.symlink_to(other)
    with pytest.raises(OSError):
        log.head(binding)


def test_imported_text_validation_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    journal_root = tmp_path / ".pd-pages"
    journal_root.mkdir()
    os.mkfifo(journal_root / "imported-text-validations.jsonl")
    binding = ImportedTextBinding(
        bundle_id="a" * 64,
        page_id="pgdp:alpha:001.png",
        page_sha256="b" * 64,
        page_head_sha256="c" * 64,
        word_id="word-1",
        text="Exact text",
        text_sha256=hashlib.sha256(b"Exact text").hexdigest(),
    )

    with pytest.raises(OSError):
        ImportedTextValidationLog(tmp_path, corpus_root=tmp_path).head(binding)


_TEXT_SHA256 = hashlib.sha256("caf\u00e9".encode()).hexdigest()
_PAGE_ONE_ID = "5c7e6cda-0f5e-4ced-9b61-c459f89e2ad1"
_PAGE_TWO_ID = "40d00c3d-18bd-4d0f-a689-c7ce52fc7dd2"


def _correction(*, revision: int = 1, supersedes_id: str | None = None) -> TypographyCorrection:
    base_page = "a" * 64 if revision == 1 else "e" * 64
    base_image = "b" * 64 if revision == 1 else "f" * 64
    page_head = "a" * 64 if revision == 1 else "1" * 64
    return TypographyCorrection.model_validate(
        {
            "correction_id": f"correction-{revision}",
            "word_id": stable_word_id(
                project_id="project", page_id="page-1", reading_order=3, text="caf\u00e9"
            ),
            "revision": revision,
            "supersedes_id": supersedes_id,
            "base_page_sha256": base_page,
            "base_image_sha256": base_image,
            "base_text_sha256": _TEXT_SHA256,
            "base_word_revision": revision - 1,
            "replacement_text_sha256": _TEXT_SHA256,
            "replacement_page_sha256": "e" * 64,
            "replacement_image_sha256": "f" * 64,
            "replacement_page_head_sha256": "1" * 64,
            "replacement_word_revision": revision,
            "taxonomy_version": "launch-1",
            "taxonomy_hash": "2" * 64,
            "grapheme_map_version": GRAPHEME_SEGMENTATION_VERSION,
            "page_head_sha256": page_head,
            "labeler_id": "reviewer@example.test",
            "decision": "approved_edit",
            "replacement": {
                "word_id": stable_word_id(
                    project_id="project", page_id="page-1", reading_order=3, text="caf\u00e9"
                ),
                "text": "caf\u00e9",
                "text_sha256": _TEXT_SHA256,
                "page_content_sha256": "e" * 64,
                "image_artifact_sha256": "f" * 64,
                "grapheme_map_version": GRAPHEME_SEGMENTATION_VERSION,
                "taxonomy_version": "launch-1",
                "taxonomy_hash": "2" * 64,
                "label_states": {"italic": "positive", "bold": "negative"},
                "spans": [
                    {
                        "span_id": "span-1",
                        "label": "italic",
                        "start": 0,
                        "end": 4,
                        "label_source": "human",
                        "confidence_tier": "gold",
                        "alignment_evidence_id": "human-review",
                    }
                ],
                "source_evidence_ids": ["human-review"],
                "whole_word_labels": ["italic"],
                "word_revision": revision,
                "review_state": "reviewed",
            },
        }
    )


def _binding(*, word_revision: int = 0) -> TypographyBinding:
    return TypographyBinding(
        page_sha256="a" * 64,
        image_sha256="b" * 64,
        text_sha256=_TEXT_SHA256,
        page_head_sha256="a" * 64,
        word_revision=word_revision,
    )


def _rebound_correction(
    template: TypographyCorrection,
    *,
    correction_id: str,
    word_id: str,
    revision: int,
    supersedes_id: str | None,
    base_page: str,
    base_image: str,
    base_text: str,
    base_head: str,
    base_word_revision: int,
    replacement_page: str,
    replacement_image: str,
    replacement_text: str,
    replacement_head: str,
) -> TypographyCorrection:
    payload = template.model_dump(mode="json")
    replacement = payload["replacement"]
    assert isinstance(replacement, dict)
    replacement.update(
        {
            "word_id": word_id,
            "page_content_sha256": replacement_page,
            "image_artifact_sha256": replacement_image,
            "text_sha256": replacement_text,
            "word_revision": revision,
        }
    )
    payload.update(
        {
            "correction_id": correction_id,
            "word_id": word_id,
            "revision": revision,
            "supersedes_id": supersedes_id,
            "base_page_sha256": base_page,
            "base_image_sha256": base_image,
            "base_text_sha256": base_text,
            "page_head_sha256": base_head,
            "base_word_revision": base_word_revision,
            "replacement_page_sha256": replacement_page,
            "replacement_image_sha256": replacement_image,
            "replacement_text_sha256": replacement_text,
            "replacement_page_head_sha256": replacement_head,
            "replacement_word_revision": revision,
            "replacement": replacement,
        }
    )
    return TypographyCorrection.model_validate(payload)


def test_stable_word_id_is_deterministic_and_text_sensitive() -> None:
    first = stable_word_id(project_id="p", page_id="page", reading_order=2, text="a")
    assert first == stable_word_id(project_id="p", page_id="page", reading_order=2, text="a")
    assert first != stable_word_id(project_id="p", page_id="page", reading_order=2, text="b")


def test_stable_page_id_survives_ocr_aggregate_replacement() -> None:
    first = stable_page_id(project_id="project", page_index=7)
    assert first == stable_page_id(project_id="project", page_index=7)
    assert first != stable_page_id(project_id="project", page_index=8)


def test_log_appends_canonical_json_and_recovers_head(tmp_path: Path) -> None:
    log = TypographyCorrectionLog(tmp_path)
    correction = _correction()

    log.append(correction, logical_page_id=_PAGE_ONE_ID, current=_binding())

    assert log.head(_PAGE_ONE_ID, correction.word_id) == correction
    line = (tmp_path / ".pd-pages" / "typography-corrections.jsonl").read_text().strip()
    record = json.loads(line)
    assert record["schema_version"] == 1
    assert record["logical_page_id"] == _PAGE_ONE_ID
    assert record["correction"]["correction_id"] == "correction-1"


def test_log_rejects_stale_page_binding_without_writing(tmp_path: Path) -> None:
    log = TypographyCorrectionLog(tmp_path)
    correction = _correction()

    with pytest.raises(StaleTypographyBindingError, match="base_page_sha256"):
        log.append(
            correction,
            logical_page_id=_PAGE_ONE_ID,
            current=_binding().model_copy(update={"page_sha256": "9" * 64}),
        )

    assert (tmp_path / ".pd-pages" / "typography-corrections.jsonl").read_bytes() == b""


def test_log_requires_linear_revision_and_supersedes_chain(tmp_path: Path) -> None:
    log = TypographyCorrectionLog(tmp_path)
    first = _correction()
    log.append(first, logical_page_id=_PAGE_ONE_ID, current=_binding())

    with pytest.raises(StaleTypographyBindingError, match="supersedes_id"):
        log.append(
            _correction(revision=2, supersedes_id="wrong-correction"),
            logical_page_id=_PAGE_ONE_ID,
            current=_binding(word_revision=1),
        )

    second = _correction(revision=2, supersedes_id=first.correction_id)
    # Successor validation uses the persisted effective head, not this stale value.
    log.append(second, logical_page_id=_PAGE_ONE_ID, current=_binding(word_revision=1))
    assert log.head(_PAGE_ONE_ID, first.word_id) == second


def test_log_rejects_successor_whose_base_does_not_match_persisted_head(tmp_path: Path) -> None:
    log = TypographyCorrectionLog(tmp_path)
    first = _correction()
    log.append(first, logical_page_id=_PAGE_ONE_ID, current=_binding())
    stale = _correction(revision=2, supersedes_id=first.correction_id).model_copy(
        update={"base_page_sha256": "a" * 64}
    )

    with pytest.raises(StaleTypographyBindingError, match="base_page_sha256"):
        log.append(stale, logical_page_id=_PAGE_ONE_ID, current=_binding(word_revision=1))


def test_global_page_head_and_per_word_lineage_advance_independently(tmp_path: Path) -> None:
    log = TypographyCorrectionLog(tmp_path)
    word_a_first = _correction()
    log.append(word_a_first, logical_page_id=_PAGE_ONE_ID, current=_binding())

    word_b_id = stable_word_id(project_id="project", page_id="page-1", reading_order=4, text="tea")
    word_b_first = _rebound_correction(
        word_a_first,
        correction_id="word-b-1",
        word_id=word_b_id,
        revision=1,
        supersedes_id=None,
        base_page=word_a_first.effective_page_sha256,
        base_image=word_a_first.effective_image_sha256,
        base_text=word_a_first.effective_text_sha256,
        base_head=word_a_first.effective_page_head_sha256,
        base_word_revision=0,
        replacement_page="3" * 64,
        replacement_image="4" * 64,
        replacement_text=_TEXT_SHA256,
        replacement_head="5" * 64,
    )
    log.append(word_b_first, logical_page_id=_PAGE_ONE_ID, current=_binding())

    stale_a = _correction(revision=2, supersedes_id=word_a_first.correction_id)
    with pytest.raises(StaleTypographyBindingError, match="base_page_sha256"):
        log.append(stale_a, logical_page_id=_PAGE_ONE_ID, current=_binding(word_revision=1))

    word_a_second = _rebound_correction(
        word_a_first,
        correction_id="word-a-2",
        word_id=word_a_first.word_id,
        revision=2,
        supersedes_id=word_a_first.correction_id,
        base_page=word_b_first.effective_page_sha256,
        base_image=word_b_first.effective_image_sha256,
        base_text=word_b_first.effective_text_sha256,
        base_head=word_b_first.effective_page_head_sha256,
        base_word_revision=word_a_first.effective_word_revision,
        replacement_page="6" * 64,
        replacement_image="7" * 64,
        replacement_text=_TEXT_SHA256,
        replacement_head="8" * 64,
    )
    log.append(word_a_second, logical_page_id=_PAGE_ONE_ID, current=_binding())

    assert log.head(_PAGE_ONE_ID, word_a_first.word_id) == word_a_second
    assert log.head(_PAGE_ONE_ID, word_b_id) == word_b_first


def test_page_heads_and_same_word_lineage_are_isolated_across_pages(tmp_path: Path) -> None:
    log = TypographyCorrectionLog(tmp_path)
    page_one = _correction()
    page_two = page_one.model_copy(update={"correction_id": "page-two-correction"})

    log.append(page_one, logical_page_id=_PAGE_ONE_ID, current=_binding())
    log.append(page_two, logical_page_id=_PAGE_TWO_ID, current=_binding())

    reloaded = TypographyCorrectionLog(tmp_path)
    assert reloaded.head(_PAGE_ONE_ID, page_one.word_id) == page_one
    assert reloaded.head(_PAGE_TWO_ID, page_two.word_id) == page_two


def test_log_rejects_tampered_envelope_logical_page_id(tmp_path: Path) -> None:
    log = TypographyCorrectionLog(tmp_path)
    log.path.parent.mkdir()
    log.path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "logical_page_id": "not-a-uuid",
                "correction": _correction().model_dump(mode="json"),
            }
        )
        + "\n"
    )

    with pytest.raises(ValueError, match="logical_page_id"):
        log.head(_PAGE_ONE_ID, _correction().word_id)


def test_append_does_not_recover_valid_json_with_tampered_envelope(tmp_path: Path) -> None:
    log = TypographyCorrectionLog(tmp_path)
    log.path.parent.mkdir()
    tampered = json.dumps(
        {
            "schema_version": 1,
            "logical_page_id": "not-a-uuid",
            "correction": _correction().model_dump(mode="json"),
        }
    ).encode()
    log.path.write_bytes(tampered)

    with pytest.raises(ValueError, match="logical_page_id"):
        log.append(_correction(), logical_page_id=_PAGE_ONE_ID, current=_binding())

    assert log.path.read_bytes() == tampered


def test_log_refuses_ambiguous_legacy_bare_correction(tmp_path: Path) -> None:
    log = TypographyCorrectionLog(tmp_path)
    log.path.parent.mkdir()
    log.path.write_text(json.dumps(_correction().model_dump(mode="json")) + "\n")

    with pytest.raises(ValueError, match="legacy bare typography correction"):
        log.head(_PAGE_ONE_ID, _correction().word_id)


def test_mixed_legacy_and_envelope_rows_reject_without_mutation(tmp_path: Path) -> None:
    correction = _correction()
    log = TypographyCorrectionLog(tmp_path)
    log.path.parent.mkdir()
    original = (
        json.dumps(correction.model_dump(mode="json"))
        + "\n"
        + json.dumps(
            {
                "schema_version": 1,
                "logical_page_id": _PAGE_ONE_ID,
                "correction": correction.model_dump(mode="json"),
            }
        )
        + "\n"
    ).encode()
    log.path.write_bytes(original)

    with pytest.raises(ValueError, match="repair or export"):
        log.append(correction, logical_page_id=_PAGE_ONE_ID, current=_binding())

    assert log.path.read_bytes() == original


@pytest.mark.parametrize("leaf_kind", ["symlink", "fifo"])
def test_log_rejects_non_regular_journal(tmp_path: Path, leaf_kind: str) -> None:
    journal_dir = tmp_path / ".pd-pages"
    journal_dir.mkdir()
    journal = journal_dir / "typography-corrections.jsonl"
    if leaf_kind == "symlink":
        journal.symlink_to(tmp_path / "outside")
    else:
        os.mkfifo(journal)

    with pytest.raises(OSError):
        TypographyCorrectionLog(tmp_path).append(
            _correction(), logical_page_id=_PAGE_ONE_ID, current=_binding()
        )


def test_log_rejects_symlink_journal_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".pd-pages").symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError):
        TypographyCorrectionLog(tmp_path).append(
            _correction(), logical_page_id=_PAGE_ONE_ID, current=_binding()
        )


def test_log_rejects_project_outside_corpus_root(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    project = tmp_path / "outside-project"
    corpus.mkdir()
    project.mkdir()

    with pytest.raises(ValueError, match="contained"):
        TypographyCorrectionLog(project, corpus_root=corpus)


def test_log_rejects_symlink_project_inside_corpus(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    outside = tmp_path / "outside"
    corpus.mkdir()
    outside.mkdir()
    project = corpus / "project"
    project.symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError):
        TypographyCorrectionLog(project, corpus_root=corpus).append(
            _correction(), logical_page_id=_PAGE_ONE_ID, current=_binding()
        )


def test_log_recovers_only_invalid_unterminated_trailing_record(tmp_path: Path) -> None:
    log = TypographyCorrectionLog(tmp_path)
    first = _correction()
    log.append(first, logical_page_id=_PAGE_ONE_ID, current=_binding())
    with log.path.open("ab") as stream:
        stream.write(b'{"correction_id":"partial"')

    second = _correction(revision=2, supersedes_id=first.correction_id)
    log.append(second, logical_page_id=_PAGE_ONE_ID, current=_binding(word_revision=1))

    assert log.head(_PAGE_ONE_ID, first.word_id) == second
    recovery = log.recovery_path.read_text()
    assert hashlib.sha256(b'{"correction_id":"partial"').hexdigest() in recovery


def test_log_rejects_interior_corruption(tmp_path: Path) -> None:
    log = TypographyCorrectionLog(tmp_path)
    log.path.parent.mkdir()
    log.path.write_bytes(b"not-json\nmore-not-json")

    with pytest.raises(ValueError):
        log.append(_correction(), logical_page_id=_PAGE_ONE_ID, current=_binding())


def test_publish_export_failure_leaves_no_final_or_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = TypographyCorrectionLog(tmp_path)

    def fail_rename(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(os, "rename", fail_rename)
    with pytest.raises(OSError, match="simulated rename failure"):
        log.publish_export("bundle.json", b"complete export")

    export_root = tmp_path / ".pd-pages" / "typography-exports"
    assert not (export_root / "bundle.json").exists()
    assert list(export_root.iterdir()) == []


def test_concurrent_immutable_export_is_never_truncated(tmp_path: Path) -> None:
    log = TypographyCorrectionLog(tmp_path)
    payloads = (b"a" * 131_071, b"b" * 131_073)

    def publish(payload: bytes) -> None:
        with suppress(FileExistsError):
            log.publish_export("bundle.json", payload)

    with ThreadPoolExecutor(max_workers=2) as executor:
        tuple(executor.map(publish, payloads))

    published = (tmp_path / ".pd-pages" / "typography-exports" / "bundle.json").read_bytes()
    assert published in payloads
    assert not any(
        path.name.endswith(".tmp") for path in (tmp_path / ".pd-pages" / "typography-exports").iterdir()
    )


def test_publish_export_rejects_existing_fifo_without_blocking(tmp_path: Path) -> None:
    export_root = tmp_path / ".pd-pages" / "typography-exports"
    export_root.mkdir(parents=True)
    os.mkfifo(export_root / "bundle.json")
    log = TypographyCorrectionLog(tmp_path)

    def timeout_handler(_signal_number: int, _frame: object) -> None:
        raise TimeoutError("export FIFO read blocked")

    previous_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(1)
    try:
        with pytest.raises(OSError, match="regular file"):
            log.publish_export("bundle.json", b"payload")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)
