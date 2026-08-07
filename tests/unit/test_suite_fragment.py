"""The packaged ``pdomain-suite.json`` fragment must exist and be valid.

``pdomain_ops.suite.register_self()`` reads this resource out of the installed
package at every server start and raises ``FileNotFoundError`` when it is
absent, so a missing fragment makes ``pdomain-ocr-labeler-ui`` fail before
uvicorn binds a socket. Every CLI test in ``test_main_cli.py`` patches
``register_self`` out, which is precisely why the fragment could go missing
without a red test — these assertions exercise the real resource instead.
"""

from __future__ import annotations

import importlib.resources
import json
from typing import Any

from pdomain_ops.suite.types import SuiteApp

from pdomain_ocr_labeler_spa.__main__ import _DEFAULT_PORT

_APP_ID = "pdomain-ocr-labeler-spa"


def _fragment() -> dict[str, Any]:
    raw = (importlib.resources.files("pdomain_ocr_labeler_spa") / "pdomain-suite.json").read_text(
        encoding="utf-8"
    )
    parsed: dict[str, Any] = json.loads(raw)
    return parsed


def test_fragment_is_shipped_and_parses_as_a_suite_app() -> None:
    """register_self() must find a fragment that satisfies the suite schema."""
    app = SuiteApp(**_fragment())

    assert app.app_id == _APP_ID
    assert app.package == _APP_ID
    assert app.display_name
    assert app.icon


def test_fragment_default_port_matches_the_cli_default() -> None:
    """A drifting port would register a launch URL the server never binds."""
    assert _fragment()["default_port"] == _DEFAULT_PORT
