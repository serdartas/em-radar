"""Regression guard: the default docker-compose.yml must bind only to localhost.

If this test fails it means the ports mapping was changed back to a LAN-wide
binding (e.g. "8080:8080" or "0.0.0.0:8080:8080"), which exposes the app on
the network by default. EM Radar has no authentication in the current release,
so the default must be 127.0.0.1-only (REQ-NF-010).
"""

from pathlib import Path

import yaml


def _compose_path() -> Path:
    # Walk up from this file to the repo root (contains deploy/docker/docker-compose.yml).
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "deploy" / "docker" / "docker-compose.yml"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Could not locate deploy/docker/docker-compose.yml from test file")


def test_emradar_service_binds_only_to_localhost() -> None:
    compose = yaml.safe_load(_compose_path().read_text())

    ports: list[str] = compose["services"]["emradar"]["ports"]

    for mapping in ports:
        assert mapping.startswith("127.0.0.1:"), (
            f"Port mapping {mapping!r} is not restricted to localhost (127.0.0.1). "
            "The default docker-compose.yml must bind to 127.0.0.1 only "
            "(REQ-NF-010). Change it back to '127.0.0.1:8080:8080'."
        )
        assert not mapping.startswith("0.0.0.0:"), (
            f"Port mapping {mapping!r} uses 0.0.0.0, which exposes the app on the LAN. "
            "This must not be the default. See README.md for the opt-in override."
        )
        assert mapping != "8080:8080", (
            "Port mapping '8080:8080' binds to all interfaces by default. "
            "Use '127.0.0.1:8080:8080' instead."
        )
