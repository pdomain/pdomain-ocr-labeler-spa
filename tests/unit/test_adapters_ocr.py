"""OCR adapter Protocol + stub impls shape pins.

Spec: ``docs/architecture/02-backend.md §1`` (full adapter axis,
``local_doctr | modal | shared_container``), ``§7`` (`IOCREngine`
Protocol signature), ``specs/17-decisions.md D-018`` (the seam is real
in v1 even though only ``local_doctr`` is wired).

This iteration ships the Protocol + the three impl module skeletons.
``local_doctr.ocr_page`` is left as ``raise NotImplementedError`` (the
real wiring lands in M3); ``modal`` and ``shared_container`` raise the
spec-named ``NotImplementedYet`` so a misconfigured ``Settings.ocr_engine``
fails loudly with a recognisable error.
"""

from __future__ import annotations

import inspect

import pytest


def test_iocrengine_protocol_module_exports() -> None:
    from pd_ocr_labeler_spa.adapters import ocr

    assert hasattr(ocr, "IOCREngine"), "IOCREngine must be re-exported"
    assert hasattr(ocr, "LocalDoctrOCR"), "LocalDoctrOCR stub must be re-exported"
    assert hasattr(ocr, "ModalOCR"), "ModalOCR stub must be re-exported"
    assert hasattr(ocr, "SharedContainerOCR"), "SharedContainerOCR stub must be re-exported"


def test_iocrengine_protocol_method_set() -> None:
    from pd_ocr_labeler_spa.adapters.ocr.base import IOCREngine

    methods = {
        name for name, _ in inspect.getmembers(IOCREngine, predicate=callable) if not name.startswith("_")
    }
    assert "ocr_page" in methods


def test_ocr_impls_conform_structurally_not_by_inheritance() -> None:
    """B-46 policy pin: OCR impls don't inherit from the Protocol.

    ``adapters/__init__.py`` documents that conformance is structural
    (PEP 544): impls must NOT subclass the Protocol class. This pin
    catches a future "consistency" change that re-adds inheritance
    (which would shadow Protocol class attributes and silently change
    default-argument resolution). ``isinstance(impl, IOCREngine)`` still
    works at runtime via ``@runtime_checkable``.
    """
    from pd_ocr_labeler_spa.adapters.ocr.base import IOCREngine
    from pd_ocr_labeler_spa.adapters.ocr.local_doctr import LocalDoctrOCR
    from pd_ocr_labeler_spa.adapters.ocr.modal import ModalOCR
    from pd_ocr_labeler_spa.adapters.ocr.shared_container import SharedContainerOCR

    for impl in (LocalDoctrOCR, ModalOCR, SharedContainerOCR):
        assert IOCREngine not in impl.__mro__, (
            f"{impl.__name__} should NOT subclass IOCREngine — adapters/__init__.py "
            f"documents structural-only conformance (B-46). MRO: {impl.__mro__}"
        )
        # And structural conformance still holds:
        assert isinstance(impl(), IOCREngine), f"{impl.__name__} fails the runtime_checkable structural check"


def test_modal_ocr_raises_not_implemented_yet() -> None:
    """Spec §7: ``modal.py`` raises ``NotImplementedYet``."""
    import asyncio

    from pd_ocr_labeler_spa.adapters.ocr.modal import ModalOCR
    from pd_ocr_labeler_spa.core.exceptions import NotImplementedYet

    eng = ModalOCR()

    async def _go() -> None:
        with pytest.raises(NotImplementedYet, match="modal"):
            await eng.ocr_page(  # type: ignore[arg-type]
                None,
                detection_key="db_resnet50",
                recognition_key="crnn_vgg16_bn",
                hf_revision=None,
            )

    asyncio.run(_go())


def test_shared_container_ocr_raises_not_implemented_yet() -> None:
    import asyncio

    from pd_ocr_labeler_spa.adapters.ocr.shared_container import SharedContainerOCR
    from pd_ocr_labeler_spa.core.exceptions import NotImplementedYet

    eng = SharedContainerOCR()

    async def _go() -> None:
        with pytest.raises(NotImplementedYet, match="shared_container"):
            await eng.ocr_page(  # type: ignore[arg-type]
                None,
                detection_key="db_resnet50",
                recognition_key="crnn_vgg16_bn",
                hf_revision=None,
            )

    asyncio.run(_go())


def test_local_doctr_ocr_is_stub_until_m3() -> None:
    """``local_doctr`` ships scaffolded; real impl lands in M3.

    Until then ``ocr_page`` raises ``NotImplementedError`` — distinct
    from ``NotImplementedYet`` (which is for never-going-to-be-wired
    backends in v1). Pinning this distinction prevents an M3 author
    from accidentally weakening the v1 stubs to the same "not wired"
    error.
    """
    import asyncio

    from pd_ocr_labeler_spa.adapters.ocr.local_doctr import LocalDoctrOCR

    eng = LocalDoctrOCR()

    async def _go() -> None:
        # Bare NotImplementedError, NOT NotImplementedYet — different semantic.
        with pytest.raises(NotImplementedError):
            await eng.ocr_page(  # type: ignore[arg-type]
                None,
                detection_key="db_resnet50",
                recognition_key="crnn_vgg16_bn",
                hf_revision=None,
            )

    asyncio.run(_go())


def test_not_implemented_yet_is_distinct_exception() -> None:
    """``NotImplementedYet`` is its own exception, subclass of NotImplementedError.

    Subclassing NotImplementedError keeps generic catch-handlers working
    while letting callers grep the spec-named class for "wired-later"
    seams without confusion with one-off TODOs.
    """
    from pd_ocr_labeler_spa.core.exceptions import NotImplementedYet

    assert issubclass(NotImplementedYet, NotImplementedError)
