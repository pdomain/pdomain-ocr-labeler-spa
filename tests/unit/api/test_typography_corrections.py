from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pdomain_book_tools.typography import (
    GRAPHEME_SEGMENTATION_VERSION,
    REVIEW_CONTRACT_VERSION,
    ArtifactReference,
    CorrectionBundle,
    Evidence,
    LabelingBundle,
    LabelState,
    ReviewState,
    TypographyTaxonomy,
    WordTypography,
)

from pdomain_ocr_labeler_spa.api.typography import TYPOGRAPHY_TAXONOMY
from pdomain_ocr_labeler_spa.bootstrap import build_app
from pdomain_ocr_labeler_spa.core.models import PageSource, Project
from pdomain_ocr_labeler_spa.core.page_state import PageLoadOutcome
from pdomain_ocr_labeler_spa.core.persistence.labeling_bundle import LoadedLabelingBundle
from pdomain_ocr_labeler_spa.core.project_state import PageState
from pdomain_ocr_labeler_spa.core.typography_review import (
    TypographyCorrectionLog,
    stable_page_id,
    stable_word_id,
)
from pdomain_ocr_labeler_spa.settings import Settings


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _client(tmp_path: Path) -> tuple[TestClient, str, str]:
    project_root = tmp_path / "alpha"
    project_root.mkdir()
    image = project_root / "page001.png"
    image.write_bytes(b"image")
    project_id = "alpha"
    page_id = stable_page_id(project_id=project_id, page_index=0)
    word_id = stable_word_id(project_id=project_id, page_id=page_id, reading_order=0, text="Word")
    app = build_app(Settings(mode="api_only", data_root=tmp_path / "data"))
    app.state.project_state.set_loaded_project(
        Project(
            project_id=project_id,
            project_root=project_root,
            image_paths=[image],
            ground_truth_map={image.name: "Word"},
            total_pages=1,
        )
    )
    app.state.active_project_carrier.set_active_project(project_root)
    client = TestClient(app)
    _set_current_page(client, words=[("Word", True)])
    return client, page_id, word_id


def _client_two_words(tmp_path: Path) -> tuple[TestClient, str, str, str]:
    client, page_id, first_word_id = _client(tmp_path)
    project = client.app.state.project_state.loaded_project
    assert project is not None
    project.ground_truth_map["page001.png"] = "Alpha Beta"
    _set_current_page(client, words=[("Alpha", True), ("Beta", True)])
    second_word_id = stable_word_id(project_id="alpha", page_id=page_id, reading_order=1, text="Beta")
    first_word_id = stable_word_id(project_id="alpha", page_id=page_id, reading_order=0, text="Alpha")
    return client, page_id, first_word_id, second_word_id


def _taxonomy() -> TypographyTaxonomy:
    return TYPOGRAPHY_TAXONOMY


def _label_states(value: LabelState) -> dict[str, LabelState]:
    return {label.value: value for label in _taxonomy().labels}


def _set_current_page(
    client: TestClient,
    *,
    words: list[tuple[str, bool]],
) -> None:
    page_words = [
        SimpleNamespace(
            text=f"ocr-{index}",
            ground_truth_text=text,
            word_labels=["validated"] if validated else [],
        )
        for index, (text, validated) in enumerate(words)
    ]
    page = SimpleNamespace(
        words=page_words,
        lines=[SimpleNamespace(words=page_words)],
        to_dict=lambda: {
            "words": [
                {
                    "text": word.text,
                    "ground_truth_text": word.ground_truth_text,
                    "word_labels": word.word_labels,
                }
                for word in page_words
            ]
        },
    )
    client.app.state.project_state.set_page_state(  # type: ignore[attr-defined]
        0,
        PageState(
            page_index=0,
            page_record=PageLoadOutcome(page_index=0, source=PageSource.FILESYSTEM, payload=page),
        ),
    )


def test_head_binding_uses_current_persisted_ground_truth_and_page_content(tmp_path: Path) -> None:
    client, page_id, _word_id = _client(tmp_path)
    _set_current_page(client, words=[("Corrected", True)])
    corrected_word_id = stable_word_id(project_id="alpha", page_id=page_id, reading_order=0, text="Corrected")

    response = client.get(f"/api/projects/alpha/pages/0/typography/words/{corrected_word_id}/head")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == "Corrected"
    assert body["text_sha256"] == _sha("Corrected")
    assert body["page_sha256"] != _sha("Word")


def test_historical_replacement_never_overrides_current_persisted_head_text(tmp_path: Path) -> None:
    client, _page_id, word_id = _client(tmp_path)
    path = f"/api/projects/alpha/pages/0/typography/words/{word_id}"
    initial = client.get(f"{path}/head").json()
    submitted = client.post(
        f"{path}/corrections",
        json=_accepted_edit(initial, correction_id="historical-edit", text="Historical"),
    )
    assert submitted.status_code == 200, submitted.text

    current = client.get(f"{path}/head")

    assert current.status_code == 200
    assert current.json()["text"] == "Word"
    assert current.json()["text_sha256"] == _sha("Word")


def test_review_requires_persisted_text_validation_not_typography_replacement(tmp_path: Path) -> None:
    client, page_id, _word_id = _client(tmp_path)
    _set_current_page(client, words=[("Word", False)])
    word_id = stable_word_id(project_id="alpha", page_id=page_id, reading_order=0, text="Word")
    path = f"/api/projects/alpha/pages/0/typography/words/{word_id}"
    with client:
        head = client.get(f"{path}/head").json()
        response = client.post(
            f"{path}/corrections",
            json=_accepted_edit(head, correction_id="typography-only", text="Word"),
        )
        assert response.status_code == 200, response.text

        review = client.get("/api/projects/alpha/pages/0/typography/review").json()

    assert review["text_reviewed_words"] == 0
    assert review["typography_reviewed_words"] == 1
    assert review["complete"] is False


def test_default_correction_export_rejects_unvalidated_text(tmp_path: Path) -> None:
    client, _page_id, word_id = _client(tmp_path)
    _set_current_page(client, words=[("Word", False)])
    path = f"/api/projects/alpha/pages/0/typography/words/{word_id}"
    with client:
        head = client.get(f"{path}/head").json()
        assert (
            client.post(
                f"{path}/corrections",
                json=_accepted_edit(head, correction_id="typography-only", text="Word"),
            ).status_code
            == 200
        )
        response = client.post(
            "/api/projects/alpha/pages/0/typography/correction-bundles/export",
            json={"labeling_bundle": _labeling_bundle(head, word_id).model_dump(mode="json")},
        )

    assert response.status_code == 422


def test_empty_persisted_page_is_complete_for_text_and_typography(tmp_path: Path) -> None:
    client, _page_id, _word_id = _client(tmp_path)
    _set_current_page(client, words=[])

    review = client.get("/api/projects/alpha/pages/0/typography/review")

    assert review.status_code == 200
    assert review.json() | {"heads": []} == review.json()
    assert review.json()["total_words"] == 0
    assert review.json()["text_reviewed_words"] == 0
    assert review.json()["typography_reviewed_words"] == 0
    assert review.json()["blocked_words"] == 0
    assert review.json()["complete"] is True


def test_head_returns_server_segmented_extended_graphemes(tmp_path: Path) -> None:
    client, _page_id, word_id = _client(tmp_path)
    project = client.app.state.project_state.loaded_project
    assert project is not None
    project.ground_truth_map["page001.png"] = "a\u0301👨‍👩‍👧‍👦"
    _set_current_page(client, words=[("a\u0301👨‍👩‍👧‍👦", True)])
    word_id = stable_word_id(
        project_id="alpha",
        page_id=stable_page_id(project_id="alpha", page_index=0),
        reading_order=0,
        text="a\u0301👨‍👩‍👧‍👦",
    )

    response = client.get(f"/api/projects/alpha/pages/0/typography/words/{word_id}/head")

    assert response.status_code == 200
    assert response.json()["text"] == "a\u0301👨‍👩‍👧‍👦"
    assert response.json()["graphemes"] == ["a\u0301", "👨‍👩‍👧‍👦"]


def test_append_rejects_tampered_contract_and_unknown_label(tmp_path: Path) -> None:
    client, _page_id, word_id = _client(tmp_path)
    path = f"/api/projects/alpha/pages/0/typography/words/{word_id}"
    head = client.get(f"{path}/head").json()
    tampered = _accepted_edit(head, correction_id="tampered", text="Word")
    tampered["taxonomy_hash"] = "f" * 64
    assert client.post(f"{path}/corrections", json=tampered).status_code == 422

    unknown = _accepted_edit(head, correction_id="unknown", text="Word")
    replacement = unknown["replacement"]
    assert isinstance(replacement, dict)
    replacement["label_states"]["invented-label"] = "positive"
    assert client.post(f"{path}/corrections", json=unknown).status_code in {400, 422}


def test_in_place_grapheme_review_requires_no_replacement_artifacts(tmp_path: Path) -> None:
    client, _page_id, word_id = _client(tmp_path)
    path = f"/api/projects/alpha/pages/0/typography/words/{word_id}"
    head = client.get(f"{path}/head").json()
    taxonomy = head["taxonomy"]
    response = client.post(
        f"{path}/corrections",
        json={
            "expected_head": head["head_token"],
            "correction_id": "ui-span-review",
            "taxonomy_version": taxonomy["version"],
            "taxonomy_hash": taxonomy["taxonomy_hash"],
            "grapheme_map_version": head["grapheme_map_version"],
            "decision": "approved_edit",
            "replacement_text_sha256": head["text_sha256"],
            "replacement_page_sha256": head["page_sha256"],
            "replacement_image_sha256": head["image_sha256"],
            "replacement_page_head_sha256": head["page_head_sha256"],
            "replacement_word_revision": 1,
            "replacement": {
                "word_id": word_id,
                "text": head["text"],
                "text_sha256": head["text_sha256"],
                "page_content_sha256": head["page_sha256"],
                "image_artifact_sha256": head["image_sha256"],
                "grapheme_map_version": head["grapheme_map_version"],
                "taxonomy_version": taxonomy["version"],
                "taxonomy_hash": taxonomy["taxonomy_hash"],
                "label_states": {
                    label["value"]: "positive" if label["value"] == "italic" else "negative"
                    for label in taxonomy["labels"]
                },
                "spans": [
                    {
                        "span_id": "span-1",
                        "label": "italic",
                        "start": 0,
                        "end": 1,
                        "label_source": "human",
                        "confidence_tier": "gold",
                        "alignment_evidence_id": "manual-0",
                    }
                ],
                "source_evidence_ids": ["labeler-manual-review"],
                "warnings": [],
                "word_revision": 1,
                "review_state": "reviewed",
            },
        },
    )
    assert response.status_code == 200, response.text
    current = response.json()
    rejected = client.post(
        f"{path}/corrections",
        json={
            "expected_head": current["head_token"],
            "correction_id": "later-reject",
            "taxonomy_version": taxonomy["version"],
            "taxonomy_hash": taxonomy["taxonomy_hash"],
            "grapheme_map_version": head["grapheme_map_version"],
            "decision": "reject_source",
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["text"] == "Word"
    assert rejected.json()["text_sha256"] == head["text_sha256"]


def test_reviewed_replacement_rejects_missing_required_taxonomy_state(tmp_path: Path) -> None:
    client, _page_id, word_id = _client(tmp_path)
    path = f"/api/projects/alpha/pages/0/typography/words/{word_id}"
    head = client.get(f"{path}/head").json()
    body = _accepted_edit(head, correction_id="missing-state", text="Word")
    replacement = body["replacement"]
    assert isinstance(replacement, dict)
    replacement["label_states"].pop("bold")
    response = client.post(f"{path}/corrections", json=body)
    assert response.status_code == 422


def test_progress_ignores_inactive_historical_word_identity(tmp_path: Path) -> None:
    client, _page_id, word_id = _client(tmp_path)
    path = f"/api/projects/alpha/pages/0/typography/words/{word_id}"
    head = client.get(f"{path}/head").json()
    assert (
        client.post(
            f"{path}/corrections", json=_accepted_edit(head, correction_id="old-word", text="Word")
        ).status_code
        == 200
    )
    project = client.app.state.project_state.loaded_project
    assert project is not None
    project.ground_truth_map["page001.png"] = "Replacement"
    _set_current_page(client, words=[("Replacement", True)])

    progress = client.get("/api/projects/alpha/pages/0/typography/review").json()
    assert progress["total_words"] == 1
    assert progress["reviewed_words"] == 0
    assert progress["blocked_words"] == 1
    assert progress["heads"] == []
    assert progress["complete"] is False


def _labeling_bundle(head: dict[str, object], word_id: str, *, text: str = "Word") -> LabelingBundle:
    taxonomy = _taxonomy()
    return LabelingBundle(
        schema_version=REVIEW_CONTRACT_VERSION,
        configuration_hash="c" * 64,
        taxonomy=taxonomy,
        page_id=str(head["logical_page_id"]),
        page_sha256=str(head["page_sha256"]),
        image_sha256=str(head["image_sha256"]),
        text_sha256=_sha(text),
        page_head_sha256=str(head["page_head_sha256"]),
        artifacts=(
            ArtifactReference(
                artifact_id="source-image",
                relative_path="page001.png",
                sha256=str(head["image_sha256"]),
                media_type="image/png",
            ),
        ),
        evidence=(
            Evidence(
                evidence_id="source-evidence",
                artifact_id="source-image",
                artifact_sha256=str(head["image_sha256"]),
                byte_start=0,
                byte_end=1,
            ),
        ),
        words=(
            WordTypography(
                word_id=word_id,
                text=text,
                text_sha256=_sha(text),
                page_content_sha256=str(head["page_sha256"]),
                image_artifact_sha256=str(head["image_sha256"]),
                grapheme_map_version=GRAPHEME_SEGMENTATION_VERSION,
                taxonomy_version=taxonomy.version,
                taxonomy_hash=taxonomy.taxonomy_hash,
                label_states=_label_states(LabelState.UNKNOWN),
                source_evidence_ids=("source-evidence",),
            ),
        ),
    )


def _attach_bundle(client: TestClient, bundle: LabelingBundle) -> None:
    project = client.app.state.project_state.loaded_project  # type: ignore[attr-defined]
    assert project is not None
    image = project.image_paths[0]
    page_payload = b"page-record"
    artifact_paths = {"source-image": image}
    artifact_payloads = {"source-image": image.read_bytes()}
    if hashlib.sha256(page_payload).hexdigest() == bundle.page_sha256:
        page_path = project.project_root / "page-record.json"
        page_path.write_bytes(page_payload)
        artifact_paths["page-record"] = page_path
        artifact_payloads["page-record"] = page_payload
    loaded = LoadedLabelingBundle(
        root=project.project_root,
        bundle=bundle,
        artifact_paths=artifact_paths,
        artifact_payloads=artifact_payloads,
        image_descriptor=os.open(image, os.O_RDONLY),
    )
    client.app.state.project_state.set_loaded_project(  # type: ignore[attr-defined]
        project,
        labeling_bundle=loaded,
    )


def test_bundle_worklist_preserves_native_identity_and_unvalidated_text(tmp_path: Path) -> None:
    client, _generated_page_id, generated_word_id = _client(tmp_path)
    generated_head = client.get(
        f"/api/projects/alpha/pages/0/typography/words/{generated_word_id}/head"
    ).json()
    native_word_id = "7ca20136-634e-5282-a071-0ff1c9467b8b"
    payload = _labeling_bundle(generated_head, native_word_id).model_dump(mode="python")
    page_payload = b"page-record"
    page_sha = hashlib.sha256(page_payload).hexdigest()
    page_id = "pgdp:alpha:001.png"
    page_head_payload = (
        json.dumps(
            {
                "configuration_hash": payload["configuration_hash"],
                "image_sha256": payload["image_sha256"],
                "page_id": page_id,
                "page_sha256": page_sha,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    payload.update(
        bundle_id=None,
        page_id=page_id,
        page_sha256=page_sha,
        page_head_sha256=hashlib.sha256(page_head_payload).hexdigest(),
    )
    payload["artifacts"] = (
        *payload["artifacts"],
        ArtifactReference(
            artifact_id="page-record",
            relative_path="page-record.json",
            sha256=page_sha,
            media_type="application/json",
        ),
    )
    word = payload["words"][0]
    assert isinstance(word, dict)
    word["page_content_sha256"] = page_sha
    bundle = LabelingBundle.model_validate(payload)
    _attach_bundle(client, bundle)

    response = client.get("/api/projects/alpha/pages/0/typography/worklist")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["logical_page_id"] == bundle.page_id
    assert body["bundle_id"] == bundle.bundle_id
    assert (
        body["words"][0]
        | {
            "word_id": native_word_id,
            "text": "Word",
            "graphemes": ["W", "o", "r", "d"],
            "source_review_state": "unreviewed",
            "text_reviewed": False,
            "typography_reviewed": False,
            "reviewed": False,
            "current_correction": None,
            "decision": None,
        }
        == body["words"][0]
    )
    assert body["total_words"] == 1
    assert body["complete"] is False

    head = client.get(f"/api/projects/alpha/pages/0/typography/words/{native_word_id}/head")
    assert head.status_code == 200, head.text
    assert head.json()["logical_page_id"] == bundle.page_id
    assert head.json()["page_sha256"] == bundle.page_sha256
    assert head.json()["image_sha256"] == bundle.image_sha256
    assert head.json()["text_sha256"] == bundle.words[0].text_sha256
    assert head.json()["page_head_sha256"] == bundle.page_head_sha256

    _set_current_page(client, words=[("Wo", True), ("rd", True)])
    mismatched = client.get("/api/projects/alpha/pages/0/typography/worklist")
    assert mismatched.status_code == 200
    assert mismatched.json()["text_reviewed_words"] == 0


def test_bundle_reviewed_regular_request_exports_server_published_artifacts(tmp_path: Path) -> None:
    client, _generated_page_id, generated_word_id = _client(tmp_path)
    generated_head = client.get(
        f"/api/projects/alpha/pages/0/typography/words/{generated_word_id}/head"
    ).json()
    native_word_id = "7ca20136-634e-5282-a071-0ff1c9467b8b"
    page_payload = b"page-record"
    page_sha = hashlib.sha256(page_payload).hexdigest()
    page_id = "pgdp:alpha:001.png"
    payload = _labeling_bundle(generated_head, native_word_id).model_dump(mode="python")
    page_head_payload = (
        json.dumps(
            {
                "configuration_hash": payload["configuration_hash"],
                "image_sha256": payload["image_sha256"],
                "page_id": page_id,
                "page_sha256": page_sha,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    payload.update(
        bundle_id=None,
        page_id=page_id,
        page_sha256=page_sha,
        page_head_sha256=hashlib.sha256(page_head_payload).hexdigest(),
    )
    payload["artifacts"] = (
        *payload["artifacts"],
        ArtifactReference(
            artifact_id="page-record",
            relative_path="page-record.json",
            sha256=page_sha,
            media_type="application/json",
        ),
    )
    word = payload["words"][0]
    assert isinstance(word, dict)
    word["page_content_sha256"] = page_sha
    bundle = LabelingBundle.model_validate(payload)
    _attach_bundle(client, bundle)
    _set_current_page(client, words=[("Word", True)])
    page_state = client.app.state.project_state.get_page_state(0)  # type: ignore[attr-defined]
    assert page_state is not None and page_state.page_record is not None
    page_state.page_record.payload.words[0].word_id = native_word_id
    path = f"/api/projects/alpha/pages/0/typography/words/{native_word_id}"
    head = client.get(f"{path}/head").json()
    taxonomy = head["taxonomy"]

    reviewed = client.post(
        f"{path}/corrections",
        json={
            "expected_head": head["head_token"],
            "correction_id": "ui-reviewed-regular",
            "taxonomy_version": taxonomy["version"],
            "taxonomy_hash": taxonomy["taxonomy_hash"],
            "grapheme_map_version": head["grapheme_map_version"],
            "decision": "reviewed_regular",
            "replacement": {
                "word_id": native_word_id,
                "text": "Word",
                "text_sha256": head["text_sha256"],
                "page_content_sha256": head["page_sha256"],
                "image_artifact_sha256": head["image_sha256"],
                "grapheme_map_version": head["grapheme_map_version"],
                "taxonomy_version": taxonomy["version"],
                "taxonomy_hash": taxonomy["taxonomy_hash"],
                "label_states": {label["value"]: "negative" for label in taxonomy["labels"]},
                "spans": [],
                "source_evidence_ids": ["source-evidence"],
                "word_revision": 1,
                "review_state": "reviewed_regular",
            },
            "replacement_text_sha256": head["text_sha256"],
            "replacement_page_sha256": head["page_sha256"],
            "replacement_image_sha256": head["image_sha256"],
            "replacement_page_head_sha256": head["page_head_sha256"],
            "replacement_word_revision": 1,
            "replacement_artifacts": [],
            "replacement_artifact_payloads": [],
        },
    )
    assert reviewed.status_code == 200, reviewed.text

    exported = client.post(
        "/api/projects/alpha/pages/0/typography/correction-bundles/export",
        json={},
    )

    assert exported.status_code == 200, exported.text
    artifacts = exported.json()["bundle"]["replacement_artifacts"]
    assert {artifact["sha256"] for artifact in artifacts} == {
        bundle.page_sha256,
        bundle.image_sha256,
        bundle.page_head_sha256,
    }
    export_root = tmp_path / "alpha" / ".pd-pages" / "typography-exports"
    for artifact in artifacts:
        assert (
            hashlib.sha256((export_root / artifact["relative_path"]).read_bytes()).hexdigest()
            == artifact["sha256"]
        )


def _accepted_edit(head: dict[str, object], *, correction_id: str, text: str) -> dict[str, object]:
    page_payload = f"page:{correction_id}".encode()
    text_payload = text.encode()
    image_payload = b"image"
    page_head_payload = f"page-head:{correction_id}".encode()
    page_hash = hashlib.sha256(page_payload).hexdigest()
    page_head_hash = _sha(f"page-head:{correction_id}")
    word_revision = int(head["word_revision"]) + 1
    replacement = WordTypography(
        word_id=str(head["word_id"]),
        text=text,
        text_sha256=_sha(text),
        page_content_sha256=page_hash,
        image_artifact_sha256=str(head["image_sha256"]),
        grapheme_map_version=GRAPHEME_SEGMENTATION_VERSION,
        taxonomy_version=_taxonomy().version,
        taxonomy_hash=_taxonomy().taxonomy_hash,
        label_states=_label_states(LabelState.NEGATIVE),
        source_evidence_ids=("source-evidence",),
        word_revision=word_revision,
        review_state=ReviewState.REVIEWED,
    )
    return {
        "expected_head": head["head_token"],
        "correction_id": correction_id,
        "taxonomy_version": _taxonomy().version,
        "taxonomy_hash": _taxonomy().taxonomy_hash,
        "grapheme_map_version": GRAPHEME_SEGMENTATION_VERSION,
        "decision": "approved_edit",
        "replacement": replacement.model_dump(mode="json"),
        "replacement_text_sha256": replacement.text_sha256,
        "replacement_page_sha256": page_hash,
        "replacement_image_sha256": head["image_sha256"],
        "replacement_page_head_sha256": page_head_hash,
        "replacement_word_revision": word_revision,
        "replacement_artifacts": [
            {
                "artifact_id": f"{correction_id}:text",
                "relative_path": f"{correction_id}.txt",
                "sha256": replacement.text_sha256,
                "byte_size": len(text_payload),
                "media_type": "text/plain",
            },
            {
                "artifact_id": f"{correction_id}:page",
                "relative_path": f"{correction_id}.page",
                "sha256": page_hash,
                "byte_size": len(page_payload),
                "media_type": "application/octet-stream",
            },
            {
                "artifact_id": f"{correction_id}:image",
                "relative_path": f"{correction_id}.png",
                "sha256": head["image_sha256"],
                "byte_size": len(image_payload),
                "media_type": "image/png",
            },
            {
                "artifact_id": f"{correction_id}:page-head",
                "relative_path": f"{correction_id}.page-head",
                "sha256": page_head_hash,
                "byte_size": len(page_head_payload),
                "media_type": "application/octet-stream",
            },
        ],
        "replacement_artifact_payloads": [
            {
                "artifact_id": f"{correction_id}:text",
                "data_base64": base64.b64encode(text_payload).decode(),
            },
            {
                "artifact_id": f"{correction_id}:page",
                "data_base64": base64.b64encode(page_payload).decode(),
            },
            {
                "artifact_id": f"{correction_id}:image",
                "data_base64": base64.b64encode(image_payload).decode(),
            },
            {
                "artifact_id": f"{correction_id}:page-head",
                "data_base64": base64.b64encode(page_head_payload).decode(),
            },
        ],
    }


def _two_word_labeling_bundle(
    head: dict[str, object], first_word_id: str, second_word_id: str
) -> LabelingBundle:
    taxonomy = _taxonomy()
    words = tuple(
        WordTypography(
            word_id=word_id,
            text=text,
            text_sha256=_sha(text),
            page_content_sha256=str(head["page_sha256"]),
            image_artifact_sha256=str(head["image_sha256"]),
            grapheme_map_version=GRAPHEME_SEGMENTATION_VERSION,
            taxonomy_version=taxonomy.version,
            taxonomy_hash=taxonomy.taxonomy_hash,
            label_states=_label_states(LabelState.UNKNOWN),
            source_evidence_ids=("source-evidence",),
        )
        for word_id, text in ((first_word_id, "Alpha"), (second_word_id, "Beta"))
    )
    payload = _labeling_bundle(head, first_word_id).model_dump(mode="python")
    payload.update(bundle_id=None, text_sha256=_sha("Alpha Beta"), words=words)
    return LabelingBundle.model_validate(payload)


def test_head_is_server_derived_and_post_rejects_stale_concurrent_intent(tmp_path: Path) -> None:
    client, page_id, word_id = _client(tmp_path)
    path = f"/api/projects/alpha/pages/0/typography/words/{word_id}"
    with client:
        initial = client.get(f"{path}/head")
        assert initial.status_code == 200
        head = initial.json()
        assert head["logical_page_id"] == page_id
        assert head["revision"] == 0

        body = {
            "expected_head": head["head_token"],
            "correction_id": "review-1",
            "taxonomy_version": _taxonomy().version,
            "taxonomy_hash": _taxonomy().taxonomy_hash,
            "grapheme_map_version": GRAPHEME_SEGMENTATION_VERSION,
            "decision": "reject_source",
        }
        appended = client.post(f"{path}/corrections", json=body)
        assert appended.status_code == 200
        assert appended.json()["correction"]["base_page_sha256"] == head["page_sha256"]
        assert appended.json()["revision"] == 1

        stale = client.post(f"{path}/corrections", json={**body, "correction_id": "review-2"})
        assert stale.status_code == 409

        export_path = "/api/projects/alpha/pages/0/typography/correction-bundles/export"
        export_body = {"labeling_bundle": _labeling_bundle(head, word_id).model_dump(mode="json")}
        first_export = client.post(export_path, json=export_body)
        second_export = client.post(export_path, json=export_body)
        assert first_export.status_code == second_export.status_code == 409


def test_invalid_geometry_is_a_client_error_not_a_server_error(tmp_path: Path) -> None:
    client, _page_id, word_id = _client(tmp_path)
    path = f"/api/projects/alpha/pages/0/typography/words/{word_id}"
    with client:
        head = client.get(f"{path}/head").json()
        response = client.post(
            f"{path}/corrections",
            json={
                "expected_head": head["head_token"],
                "correction_id": "bad-geometry",
                "taxonomy_version": _taxonomy().version,
                "taxonomy_hash": _taxonomy().taxonomy_hash,
                "grapheme_map_version": GRAPHEME_SEGMENTATION_VERSION,
                "decision": "reject_source",
                "geometry": [],
            },
        )
        assert response.status_code == 422


def test_export_rejects_symlinked_output_directory(tmp_path: Path) -> None:
    client, _page_id, _word_id = _client(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    pages_dir = tmp_path / "alpha" / ".pd-pages"
    pages_dir.mkdir()
    (pages_dir / "typography-exports").symlink_to(outside, target_is_directory=True)
    with client:
        response = client.post(
            "/api/projects/alpha/pages/0/typography/correction-bundles/export",
            json={
                "labeling_bundle": _labeling_bundle(
                    client.get(f"/api/projects/alpha/pages/0/typography/words/{_word_id}/head").json(),
                    _word_id,
                ).model_dump(mode="json")
            },
        )
    assert response.status_code >= 400
    assert list(outside.iterdir()) == []


def test_typography_routes_enforce_project_and_page_isolation(tmp_path: Path) -> None:
    client, _page_id, word_id = _client(tmp_path)
    with client:
        assert client.get(f"/api/projects/beta/pages/0/typography/words/{word_id}/head").status_code == 404
        assert client.get(f"/api/projects/alpha/pages/1/typography/words/{word_id}/head").status_code == 404
        assert client.get("/api/projects/../pages/0/typography/review").status_code in {404, 405}


def test_openapi_publishes_v024_geometry_and_model_enums(tmp_path: Path) -> None:
    client, _page_id, _word_id = _client(tmp_path)
    app = client.app
    assert isinstance(app, FastAPI)
    schema = app.openapi()["components"]["schemas"]
    assert schema["ModelRunPurpose"]["enum"] == ["ocr", "page_region"]
    assert schema["CoordinateTransformStage"]["enum"] == ["orientation", "crop"]
    assert "source_width" in schema["CoordinateTransform"]["properties"]
    assert "page_geometry" in schema["TypographyCorrectionSubmission"]["properties"]


def test_generated_typescript_has_exact_v024_closed_enums() -> None:
    typescript = Path("frontend/src/api/types.ts").read_text()
    assert 'ModelRunPurpose: "ocr" | "page_region";' in typescript
    assert 'CoordinateTransformStage: "orientation" | "crop";' in typescript


def test_artifact_hash_failure_does_not_advance_head(tmp_path: Path) -> None:
    client, _page_id, word_id = _client(tmp_path)
    path = f"/api/projects/alpha/pages/0/typography/words/{word_id}"
    payload = b"replacement image"
    with client:
        head = client.get(f"{path}/head").json()
        response = client.post(
            f"{path}/corrections",
            json={
                "expected_head": head["head_token"],
                "correction_id": "bad-artifact",
                "taxonomy_version": _taxonomy().version,
                "taxonomy_hash": _taxonomy().taxonomy_hash,
                "grapheme_map_version": GRAPHEME_SEGMENTATION_VERSION,
                "decision": "reject_source",
                "replacement_artifacts": [
                    {
                        "artifact_id": "replacement-image",
                        "relative_path": "replacement.png",
                        "sha256": "f" * 64,
                        "byte_size": len(payload),
                        "media_type": "image/png",
                    }
                ],
                "replacement_artifact_payloads": [
                    {
                        "artifact_id": "replacement-image",
                        "data_base64": base64.b64encode(payload).decode(),
                    }
                ],
            },
        )
        assert response.status_code == 422
        assert client.get(f"{path}/head").json()["revision"] == 0


def test_verified_artifact_is_published_before_head_advances(tmp_path: Path) -> None:
    client, _page_id, word_id = _client(tmp_path)
    path = f"/api/projects/alpha/pages/0/typography/words/{word_id}"
    payload = b"replacement image"
    payload_hash = hashlib.sha256(payload).hexdigest()
    with client:
        head = client.get(f"{path}/head").json()
        response = client.post(
            f"{path}/corrections",
            json={
                "expected_head": head["head_token"],
                "correction_id": "verified-artifact",
                "taxonomy_version": _taxonomy().version,
                "taxonomy_hash": _taxonomy().taxonomy_hash,
                "grapheme_map_version": GRAPHEME_SEGMENTATION_VERSION,
                "decision": "reject_source",
                "replacement_artifacts": [
                    {
                        "artifact_id": "replacement-image",
                        "relative_path": "replacement.png",
                        "sha256": payload_hash,
                        "byte_size": len(payload),
                        "media_type": "image/png",
                    }
                ],
                "replacement_artifact_payloads": [
                    {
                        "artifact_id": "replacement-image",
                        "data_base64": base64.b64encode(payload).decode(),
                    }
                ],
            },
        )
        assert response.status_code == 200
        assert response.json()["revision"] == 1
        exported = client.post(
            "/api/projects/alpha/pages/0/typography/correction-bundles/export",
            json={"labeling_bundle": _labeling_bundle(head, word_id).model_dump(mode="json")},
        )
        assert exported.status_code == 409
    assert (tmp_path / "alpha" / ".pd-pages" / "typography-artifacts" / payload_hash).read_bytes() == payload


def test_export_manifest_is_not_visible_until_artifacts_are_durable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _page_id, word_id = _client(tmp_path)
    path = f"/api/projects/alpha/pages/0/typography/words/{word_id}"
    with client:
        head = client.get(f"{path}/head").json()
        appended = client.post(
            f"{path}/corrections",
            json=_accepted_edit(head, correction_id="durable", text="Word"),
        )
        assert appended.status_code == 200
        original_publish = TypographyCorrectionLog.publish_export

        def fail_artifact(log: TypographyCorrectionLog, name: str, payload: bytes) -> None:
            if name.endswith(".artifact"):
                raise OSError("simulated artifact publication failure")
            original_publish(log, name, payload)

        monkeypatch.setattr(TypographyCorrectionLog, "publish_export", fail_artifact)
        exported = client.post(
            "/api/projects/alpha/pages/0/typography/correction-bundles/export",
            json={"labeling_bundle": _labeling_bundle(head, word_id).model_dump(mode="json")},
        )

    assert exported.status_code == 422
    export_root = tmp_path / "alpha" / ".pd-pages" / "typography-exports"
    assert not export_root.exists() or not any(export_root.glob("*.json"))


def test_portable_components_are_validated_without_geometry(tmp_path: Path) -> None:
    client, _page_id, word_id = _client(tmp_path)
    path = f"/api/projects/alpha/pages/0/typography/words/{word_id}"
    with client:
        head = client.get(f"{path}/head").json()
        response = client.post(
            f"{path}/corrections",
            json={
                "expected_head": head["head_token"],
                "correction_id": "bad-run",
                "taxonomy_version": _taxonomy().version,
                "taxonomy_hash": "a" * 64,
                "grapheme_map_version": GRAPHEME_SEGMENTATION_VERSION,
                "decision": "reject_source",
                "model_runs": [
                    {
                        "run_id": "ocr-1",
                        "model_name": "ocr",
                        "model_version": "1",
                        "purpose": "ocr",
                        "input_artifact_sha256": "d" * 64,
                    }
                ],
            },
        )
        assert response.status_code == 422
        assert client.get(f"{path}/head").json()["revision"] == 0


def test_rejected_head_blocks_text_and_typography_completion(tmp_path: Path) -> None:
    client, _page_id, word_id = _client(tmp_path)
    path = f"/api/projects/alpha/pages/0/typography/words/{word_id}"
    with client:
        head = client.get(f"{path}/head").json()
        response = client.post(
            f"{path}/corrections",
            json={
                "expected_head": head["head_token"],
                "correction_id": "reject",
                "taxonomy_version": _taxonomy().version,
                "taxonomy_hash": _taxonomy().taxonomy_hash,
                "grapheme_map_version": GRAPHEME_SEGMENTATION_VERSION,
                "decision": "reject_source",
            },
        )
        assert response.status_code == 200
        progress = client.get("/api/projects/alpha/pages/0/typography/review").json()
        assert progress["reviewed_words"] == 1
        assert progress["text_reviewed_words"] == 1
        assert progress["typography_reviewed_words"] == 0
        assert progress["blocked_words"] == 1
        assert progress["complete"] is False


def test_interleaved_page_global_edits_validate_and_export(tmp_path: Path) -> None:
    client, _page_id, first_word_id, second_word_id = _client_two_words(tmp_path)
    first_path = f"/api/projects/alpha/pages/0/typography/words/{first_word_id}"
    second_path = f"/api/projects/alpha/pages/0/typography/words/{second_word_id}"
    with client:
        initial = client.get(f"{first_path}/head").json()
        labeling_bundle = _two_word_labeling_bundle(initial, first_word_id, second_word_id)
        first = client.post(
            f"{first_path}/corrections",
            json=_accepted_edit(initial, correction_id="A1", text="Alpha"),
        )
        assert first.status_code == 200
        second_head = client.get(f"{second_path}/head").json()
        second = client.post(
            f"{second_path}/corrections",
            json=_accepted_edit(second_head, correction_id="B1", text="Beta"),
        )
        assert second.status_code == 200, second.text
        first_head = client.get(f"{first_path}/head").json()
        third = client.post(
            f"{first_path}/corrections",
            json=_accepted_edit(first_head, correction_id="A2", text="Alpha"),
        )
        assert third.status_code == 200
        progress = client.get("/api/projects/alpha/pages/0/typography/review")
        assert progress.status_code == 200
        assert progress.json()["text_reviewed_words"] == 2
        assert progress.json()["typography_reviewed_words"] == 2
        assert progress.json()["complete"] is True

        exported = client.post(
            "/api/projects/alpha/pages/0/typography/correction-bundles/export",
            json={
                "labeling_bundle": labeling_bundle.model_dump(mode="json"),
                "selected_word_ids": [first_word_id],
            },
        )
        assert exported.status_code == 200
        bundle = CorrectionBundle.model_validate(exported.json()["bundle"])
        assert [correction.correction_id for correction in bundle.corrections] == ["A1", "B1", "A2"]
        bundle.validate_against(labeling_bundle)
        export_root = tmp_path / "alpha" / Path(exported.json()["relative_path"]).parent
        for artifact in bundle.replacement_artifacts:
            resolved = export_root / artifact.relative_path
            assert resolved.is_file()
            assert hashlib.sha256(resolved.read_bytes()).hexdigest() == artifact.sha256


def test_same_text_line_structure_change_starts_a_distinct_page_epoch(tmp_path: Path) -> None:
    client, _page_id, first_word_id, _second_word_id = _client_two_words(tmp_path)
    path = f"/api/projects/alpha/pages/0/typography/words/{first_word_id}/head"
    before = client.get(path).json()
    page_state = client.app.state.project_state.get_page_state(0)
    assert page_state is not None and page_state.page_record is not None
    page = page_state.page_record.payload
    page.words[0].ground_truth_bounding_box = (1, 2, 3, 4)
    geometry_changed = client.get(path).json()
    assert geometry_changed["page_sha256"] != before["page_sha256"]
    del page.words[0].ground_truth_bounding_box
    page.words[0].bounding_box = (5, 6, 7, 8)
    alternate_geometry = client.get(path).json()
    assert alternate_geometry["page_sha256"] != geometry_changed["page_sha256"]
    page.lines = [
        SimpleNamespace(words=[page.words[0]]),
        SimpleNamespace(words=[page.words[1]]),
    ]

    after = client.get(path).json()

    assert after["text"] == before["text"]
    assert after["page_sha256"] != alternate_geometry["page_sha256"]


def test_text_change_starts_new_active_correction_epoch(tmp_path: Path) -> None:
    client, page_id, old_word_id = _client(tmp_path)
    old_path = f"/api/projects/alpha/pages/0/typography/words/{old_word_id}"
    with client:
        old_head = client.get(f"{old_path}/head").json()
        assert (
            client.post(
                f"{old_path}/corrections",
                json=_accepted_edit(old_head, correction_id="old-epoch", text="Word"),
            ).status_code
            == 200
        )

        _set_current_page(client, words=[("Changed", True)])
        new_word_id = stable_word_id(project_id="alpha", page_id=page_id, reading_order=0, text="Changed")
        new_path = f"/api/projects/alpha/pages/0/typography/words/{new_word_id}"
        new_head = client.get(f"{new_path}/head").json()
        assert new_head["correction"] is None
        assert (
            client.post(
                f"{new_path}/corrections",
                json=_accepted_edit(new_head, correction_id="new-epoch", text="Changed"),
            ).status_code
            == 200
        )

        progress = client.get("/api/projects/alpha/pages/0/typography/review").json()
        assert progress["reviewed_words"] == 1
        assert progress["heads"][0]["correction_id"] == "new-epoch"
        assert progress["complete"] is True
        exported = client.post(
            "/api/projects/alpha/pages/0/typography/correction-bundles/export",
            json={
                "labeling_bundle": _labeling_bundle(new_head, new_word_id, text="Changed").model_dump(
                    mode="json"
                )
            },
        )

    assert exported.status_code == 200, exported.text
    assert [row["correction_id"] for row in exported.json()["bundle"]["corrections"]] == ["new-epoch"]


def test_canonical_typography_edit_reloads_and_is_undone_by_successor(tmp_path: Path) -> None:
    client, page_id, word_id = _client(tmp_path)
    path = f"/api/projects/alpha/pages/0/typography/words/{word_id}"
    with client:
        initial = client.get(f"{path}/head").json()
        edited = client.post(
            f"{path}/corrections",
            json=_accepted_edit(initial, correction_id="edit", text="Edited"),
        )
        assert edited.status_code == 200

    project_root = tmp_path / "alpha"
    image = project_root / "page001.png"
    restarted = build_app(Settings(mode="api_only", data_root=tmp_path / "restarted-data"))
    restarted.state.project_state.set_loaded_project(
        Project(
            project_id="alpha",
            project_root=project_root,
            image_paths=[image],
            ground_truth_map={image.name: "Word"},
            total_pages=1,
        )
    )
    restarted.state.active_project_carrier.set_active_project(project_root)
    with TestClient(restarted) as restarted_client:
        reloaded = restarted_client.get(f"{path}/head")
        assert reloaded.status_code == 200
        assert reloaded.json()["page_sha256"] == initial["page_sha256"]
        assert reloaded.json()["logical_page_id"] == page_id
        assert reloaded.json()["correction"]["replacement"]["text"] == "Edited"

        undone = restarted_client.post(
            f"{path}/corrections",
            json=_accepted_edit(reloaded.json(), correction_id="undo", text="Word"),
        )
        assert undone.status_code == 200, undone.text
        assert undone.json()["correction"]["supersedes_id"] == "edit"
        assert undone.json()["correction"]["replacement"]["text"] == "Word"
