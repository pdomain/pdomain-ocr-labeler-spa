"""core/models.py must not define its own PageRecord class."""


def test_models_does_not_define_local_pagerecord() -> None:
    """core/models.py must not define its own PageRecord class."""
    import pdomain_ocr_labeler_spa.core.models as m

    pr = getattr(m, "PageRecord", None)
    if pr is None:
        return  # removed entirely — pass
    # If re-exported from ops it will not have the old local fields
    from pdomain_ops.pages import PageRecord as OpsPageRecord

    assert pr is OpsPageRecord, (
        "core/models.py defines a local PageRecord — it must import from pdomain_ops.pages"
    )
