"""The shared RotationSource enum values are part of the persisted contract."""


def test_rotation_source_values_unchanged() -> None:
    from pdomain_ops.pages import RotationSource

    assert RotationSource.NONE.value == "none"
    assert RotationSource.AUTO.value == "auto"
    assert RotationSource.MANUAL.value == "manual"
