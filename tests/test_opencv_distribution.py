"""Guard against two OpenCV distributions sharing one ``cv2/`` directory.

Every OpenCV distribution writes into ``cv2/``, so installing two of them
randomly breaks ``import cv2``. pdomain-book-tools 0.31.3 depends on
``opencv-python`` only; this test fails if anything pulls another variant in.
"""

from __future__ import annotations

from importlib.metadata import distributions

OPENCV_DISTRIBUTIONS = frozenset(
    {
        "opencv-python",
        "opencv-contrib-python",
        "opencv-python-headless",
        "opencv-contrib-python-headless",
    }
)


def test_environment_holds_only_opencv_python() -> None:
    """Exactly one OpenCV distribution, ``opencv-python``, is installed."""
    installed = {
        name.lower().replace("_", "-")
        for dist in distributions()
        if (name := dist.metadata["Name"]) is not None
    } & OPENCV_DISTRIBUTIONS
    assert installed == {"opencv-python"}
