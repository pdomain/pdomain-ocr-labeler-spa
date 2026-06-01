"""RotationSource must re-export from pdomain-ops, not define its own copy."""


def test_rotation_source_is_ops_enum() -> None:
    """Local RotationSource must re-export the ops enum, not define its own."""
    from pdomain_ops.pages import RotationSource as OpsRotationSource

    from pdomain_ocr_labeler_spa.core.models import RotationSource

    assert RotationSource is OpsRotationSource


def test_rotation_source_values_unchanged() -> None:
    from pdomain_ocr_labeler_spa.core.models import RotationSource

    assert RotationSource.NONE.value == "none"
    assert RotationSource.AUTO.value == "auto"
    assert RotationSource.MANUAL.value == "manual"
