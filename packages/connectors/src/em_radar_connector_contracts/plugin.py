# SPDX-License-Identifier: Apache-2.0

"""pytest plugin: auto-discovers em_radar.connectors entry points and provides
the ``connector_cls`` fixture so any connector package can run the shared
contract suite without copying test code.
"""

from __future__ import annotations

import importlib.metadata

import pytest


def _discover_connector_classes() -> list[type]:
    eps = importlib.metadata.entry_points(group="em_radar.connectors")
    classes = []
    for ep in sorted(eps, key=lambda e: e.name):
        cls = ep.load()  # let ImportError propagate — a broken registered connector must be visible
        classes.append(cls)
    return classes


_CONNECTOR_CLASSES = _discover_connector_classes()


@pytest.fixture(
    params=_CONNECTOR_CLASSES,
    ids=[cls.name for cls in _CONNECTOR_CLASSES],
)
def connector_cls(request: pytest.FixtureRequest) -> type:
    """Provides each registered connector class in turn for the contract suite.

    A private connector package adds an entry point under ``em_radar.connectors``
    and its connector class is automatically included in the parametrization.
    """
    return request.param  # type: ignore[return-value]
