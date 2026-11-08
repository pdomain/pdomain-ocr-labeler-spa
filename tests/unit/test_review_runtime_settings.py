from pathlib import Path

from pdomain_ocr_labeler_spa.settings import Settings


def test_tesseract_review_runtime_is_explicit_and_configurable() -> None:
    settings = Settings(
        ocr_engine="tesseract",
        tesseract_binary="/usr/bin/tesseract",
        tesseract_language="eng",
        pgdp_corpus_root=Path("/corpus"),
        source_data_python=Path("/source/bin/python"),
        source_data_timeout_s=120.0,
    )
    assert settings.ocr_engine == "tesseract"
    assert settings.tesseract_binary == "/usr/bin/tesseract"
    assert settings.tesseract_language == "eng"
    assert settings.pgdp_corpus_root == Path("/corpus")
    assert settings.source_data_python == Path("/source/bin/python")
    assert settings.source_data_timeout_s == 120.0


def test_default_ocr_provider_stays_local_doctr() -> None:
    assert Settings().ocr_engine == "local_doctr"
