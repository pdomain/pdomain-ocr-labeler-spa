"""Docker build and runtime integration tests.

Verifies the acceptance criteria for issue #252:
- `make docker-build` produces a running image
- `docker run -p 8080:8080 pd-ocr-labeler-spa` serves SPA at `/`
- `/healthz` returns 200 from the container
- Image does not include build tools or node_modules in the runtime stage
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKER_IMAGE = "pd-ocr-labeler-spa:dev"


def _have_docker() -> bool:
    """Check if docker is available."""
    return shutil.which("docker") is not None


def _have_make() -> bool:
    """Check if make is available."""
    return shutil.which("make") is not None


def _run_make_docker_build() -> None:
    """Run `make docker-build` to build the image."""
    result = subprocess.run(
        ["make", "-C", str(REPO_ROOT), "docker-build"],
        capture_output=True,
        text=True,
        timeout=600,  # 10 minutes for docker build
    )
    assert result.returncode == 0, (
        f"`make docker-build` failed (rc={result.returncode}):\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def _image_exists(image: str) -> bool:
    """Check if a Docker image exists."""
    result = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode == 0


def _get_image_history(image: str) -> str:
    """Get the history of a Docker image (for layer inspection)."""
    result = subprocess.run(
        ["docker", "image", "history", image],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"Failed to get image history: {result.stderr}"
    return result.stdout


def _run_container_and_check_healthz(image: str, port: int = 8080, timeout: int = 30) -> bool:
    """Run the container and check if /healthz returns 200.

    Returns True if healthz is reachable, False otherwise.
    Cleans up the container after testing.
    """
    container_id = None
    try:
        # Start the container in detached mode
        result = subprocess.run(
            ["docker", "run", "-d", "-p", f"{port}:8080", image],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"Failed to start container: {result.stderr}"
        container_id = result.stdout.strip()

        # Wait for the container to be ready (with timeout)
        start_time = time.time()
        while time.time() - start_time < timeout:
            health_result = subprocess.run(
                ["curl", "-f", "-s", f"http://localhost:{port}/healthz"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if health_result.returncode == 0:
                return True
            time.sleep(0.5)

        return False
    finally:
        # Clean up the container
        if container_id:
            subprocess.run(
                ["docker", "rm", "-f", container_id],
                capture_output=True,
                timeout=10,
            )


def _check_spa_served(port: int = 8080) -> bool:
    """Check if the SPA is served at / (should contain index.html content)."""
    result = subprocess.run(
        ["curl", "-f", "-s", f"http://localhost:{port}/"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if result.returncode != 0:
        return False
    # Check if response looks like an HTML page (contains html/body tags)
    return "<html" in result.stdout.lower() or "<body" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _have_make(), reason="`make` not on PATH")
@pytest.mark.skipif(not _have_docker(), reason="docker not on PATH")
class TestDockerBuild:
    """Tests for `make docker-build` producing a running image."""

    def test_make_docker_build_produces_running_image(self) -> None:
        """Verify `make docker-build` produces a running image."""
        _run_make_docker_build()
        assert _image_exists(DOCKER_IMAGE), f"Image {DOCKER_IMAGE} not found after build"

    def test_docker_run_serves_spa_at_root(self) -> None:
        """Verify `docker run -p 8080:8080 pd-ocr-labeler-spa` serves SPA at `/`."""
        _run_make_docker_build()

        # Start container and verify SPA is served
        container_id = None
        try:
            result = subprocess.run(
                ["docker", "run", "-d", "-p", "8080:8080", DOCKER_IMAGE],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0, f"Failed to start container: {result.stderr}"
            container_id = result.stdout.strip()

            # Wait for container to be ready
            time.sleep(2)

            # Check if SPA is served at /
            spa_served = _check_spa_served(8080)
            assert spa_served, "SPA not served at / from container"
        finally:
            if container_id:
                subprocess.run(
                    ["docker", "rm", "-f", container_id],
                    capture_output=True,
                    timeout=10,
                )

    def test_healthz_returns_200(self) -> None:
        """Verify `/healthz` returns 200 from the container."""
        _run_make_docker_build()

        healthz_ok = _run_container_and_check_healthz(DOCKER_IMAGE, port=8080, timeout=30)
        assert healthz_ok, "Container /healthz endpoint not returning 200"

    def test_runtime_image_excludes_build_tools_and_node_modules(self) -> None:
        """Verify image does not include build tools or node_modules in the runtime stage."""
        _run_make_docker_build()

        # The runtime stage should not have layers from the spa stage
        # (spa stage is node:24, runtime stage is python:3.13-slim)
        # We can verify by checking that there's no `npm` or `node_modules` in the final image

        # Verify by inspecting the image for the absence of certain files
        # Create a temporary container and check if node_modules exists
        result = subprocess.run(
            ["docker", "run", "--rm", DOCKER_IMAGE, "ls", "-la", "/app/node_modules"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Should fail because node_modules should not exist in runtime
        assert result.returncode != 0, (
            "node_modules found in runtime image — runtime stage should not include SPA build artifacts"
        )

        # Also check that npm/node tools aren't in the runtime
        result = subprocess.run(
            ["docker", "run", "--rm", DOCKER_IMAGE, "which", "npm"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0, "npm found in runtime image — build tools should be excluded"

        # Verify git is not in the final runtime (B-21)
        result = subprocess.run(
            ["docker", "run", "--rm", DOCKER_IMAGE, "which", "git"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0, (
            "git found in runtime image — B-21 requires git be purged from final layer"
        )
