# SPDX-License-Identifier: Apache-2.0

"""Connector contract test infrastructure.

Registers the em-radar-connector-contracts pytest plugin that auto-discovers
connectors via em_radar.connectors entry points and provides the
``connector_cls`` fixture to parametrize the contract test suite.
"""
