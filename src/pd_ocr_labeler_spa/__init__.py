"""pd-ocr-labeler-spa — FastAPI + React SPA replacement for pd-ocr-labeler.

The package ships as a single wheel with the prebuilt SPA bundled under
``pd_ocr_labeler_spa/static/``. The console script ``pd-ocr-labeler-ui``
boots a uvicorn server that serves both the REST API and the SPA. See
``specs/00-overview.md`` for the full architecture.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pd-ocr-labeler-spa")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
