"""Unit tests for ``OCRConfigCarrier`` (M3 slice 8c-iv-a).

Covers shape + invariants of the in-process carrier. Disk persistence
is deferred to slice 8c-iv-b; route-level wiring + integration is
covered in ``tests/integration/test_ocr_config_router.py``.
"""

from __future__ import annotations

import threading

import pytest

from pd_ocr_labeler_spa.core.ocr_config_state import OCRConfigCarrier


class TestDefaults:
    """Default-state contract — matches slice-8a stock-only options."""

    def test_default_detection_key_is_stock(self) -> None:
        c = OCRConfigCarrier()
        assert c.detection_key == "stock"

    def test_default_recognition_key_is_stock(self) -> None:
        c = OCRConfigCarrier()
        assert c.recognition_key == "stock"

    def test_default_hf_pinned_revision_is_none(self) -> None:
        c = OCRConfigCarrier()
        assert c.hf_pinned_revision is None

    def test_default_generation_is_zero(self) -> None:
        c = OCRConfigCarrier()
        assert c.generation == 0

    def test_snapshot_returns_default_triple(self) -> None:
        c = OCRConfigCarrier()
        assert c.snapshot() == ("stock", "stock", None)

    def test_explicit_init_overrides_defaults(self) -> None:
        c = OCRConfigCarrier(
            detection_key="hf-latest",
            recognition_key="local:foo",
            hf_pinned_revision="main",
        )
        assert c.snapshot() == ("hf-latest", "local:foo", "main")
        # Initialization is not a mutation; generation stays at 0.
        assert c.generation == 0


class TestSetModels:
    """Mutation contract — idempotent, generation bumped on real change."""

    def test_set_models_changes_state(self) -> None:
        c = OCRConfigCarrier()
        changed = c.set_models(
            detection_key="hf-latest",
            recognition_key="hf-latest",
            hf_pinned_revision="rev-1",
        )
        assert changed is True
        assert c.snapshot() == ("hf-latest", "hf-latest", "rev-1")

    def test_set_models_bumps_generation_on_change(self) -> None:
        c = OCRConfigCarrier()
        before = c.generation
        c.set_models(
            detection_key="hf-latest",
            recognition_key="stock",
            hf_pinned_revision=None,
        )
        assert c.generation == before + 1

    def test_set_models_no_op_when_state_unchanged(self) -> None:
        c = OCRConfigCarrier()
        # Storing the same default triple is a no-op.
        changed = c.set_models(
            detection_key="stock",
            recognition_key="stock",
            hf_pinned_revision=None,
        )
        assert changed is False
        assert c.generation == 0

    def test_set_models_idempotent_after_first_change(self) -> None:
        c = OCRConfigCarrier()
        c.set_models(
            detection_key="hf-latest",
            recognition_key="stock",
            hf_pinned_revision=None,
        )
        gen_after_first = c.generation
        # Re-applying the same triple does not bump generation again.
        changed = c.set_models(
            detection_key="hf-latest",
            recognition_key="stock",
            hf_pinned_revision=None,
        )
        assert changed is False
        assert c.generation == gen_after_first

    def test_set_models_distinguishes_revision_change(self) -> None:
        """A change in only ``hf_pinned_revision`` is a real change."""
        c = OCRConfigCarrier()
        c.set_models(
            detection_key="hf-latest",
            recognition_key="hf-latest",
            hf_pinned_revision="r1",
        )
        gen_before = c.generation
        changed = c.set_models(
            detection_key="hf-latest",
            recognition_key="hf-latest",
            hf_pinned_revision="r2",
        )
        assert changed is True
        assert c.generation == gen_before + 1

    def test_set_models_accepts_arbitrary_strings(self) -> None:
        """Carrier does not validate keys against an option list — that's
        the route's job. Holding an unknown key is allowed at this
        layer (the router rejects bad keys with 400 before ever calling
        the carrier; this test pins that the carrier itself is permissive
        so adding new option sources later doesn't require a carrier
        change).
        """
        c = OCRConfigCarrier()
        c.set_models(
            detection_key="some-unknown-key",
            recognition_key="another",
            hf_pinned_revision=None,
        )
        assert c.snapshot() == ("some-unknown-key", "another", None)

    def test_set_models_uses_keyword_only_args(self) -> None:
        """Positional args refused — keyword-only signature pins the call
        site against arg-order drift across the three string fields.
        """
        c = OCRConfigCarrier()
        with pytest.raises(TypeError):
            c.set_models("hf-latest", "stock", None)  # type: ignore[misc]


class TestThreadSafety:
    """Concurrent mutation must not corrupt state or skip generations."""

    def test_concurrent_distinct_writers_serialize_generation(self) -> None:
        """N threads each performing one distinct mutation → generation == N.

        If the lock were missing, two threads landing on the same value
        could both see "unchanged" and skip the bump even when the
        external observer would see two changes. We force distinct
        triples per thread so any lost update shows up as
        ``generation < N``.
        """
        c = OCRConfigCarrier()
        n = 16
        barrier = threading.Barrier(n)

        def worker(i: int) -> None:
            barrier.wait()
            c.set_models(
                detection_key=f"det-{i}",
                recognition_key=f"reco-{i}",
                hf_pinned_revision=f"rev-{i}",
            )

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert c.generation == n

    def test_snapshot_is_atomic_under_concurrent_writes(self) -> None:
        """A snapshot must reflect a single set_models call — never a
        torn read mixing fields from two distinct triples.
        """
        c = OCRConfigCarrier()
        # Pre-stamp a known triple. Workers will alternate between two
        # distinct triples; any snapshot we read must match exactly one.
        triple_a = ("det-A", "reco-A", "rev-A")
        triple_b = ("det-B", "reco-B", "rev-B")
        c.set_models(
            detection_key=triple_a[0],
            recognition_key=triple_a[1],
            hf_pinned_revision=triple_a[2],
        )

        stop = threading.Event()

        def writer() -> None:
            current = triple_a
            while not stop.is_set():
                current = triple_b if current is triple_a else triple_a
                c.set_models(
                    detection_key=current[0],
                    recognition_key=current[1],
                    hf_pinned_revision=current[2],
                )

        w = threading.Thread(target=writer)
        w.start()
        try:
            for _ in range(2_000):
                snap = c.snapshot()
                assert snap in {triple_a, triple_b}, snap
        finally:
            stop.set()
            w.join()
