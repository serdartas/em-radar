# SPDX-License-Identifier: Apache-2.0

from em_radar_connector_gitlab.connector import (
    DISCOVERY_DEFAULT_WINDOW_DAYS,
    DISCOVERY_MIN_CANDIDATES,
    DISCOVERY_WIDE_WINDOW_DAYS,
    GitLabConnector,
    GitLabConnectorConfig,
)

__all__ = [
    "DISCOVERY_DEFAULT_WINDOW_DAYS",
    "DISCOVERY_MIN_CANDIDATES",
    "DISCOVERY_WIDE_WINDOW_DAYS",
    "GitLabConnector",
    "GitLabConnectorConfig",
]
