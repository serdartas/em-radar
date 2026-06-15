from fastapi.testclient import TestClient


def test_signal_config_routes_list_patch_and_reset(api_client: TestClient) -> None:
    list_response = api_client.get("/api/signal-configs")
    assert list_response.status_code == 200
    configs = list_response.json()
    assert len(configs) == 13

    stale = next(
        config for config in configs if config["signal_id"] == "stale-in-progress-work-item"
    )
    assert stale["name"] == "Stale in-progress work item"
    assert stale["default_severity"] == "warning"
    assert stale["params_schema"]["properties"]["days_threshold"]["default"] == 7

    patch_response = api_client.patch(
        "/api/signal-configs/stale-in-progress-work-item",
        json={
            "enabled": False,
            "severity_override": "critical",
            "params": {"days_threshold": 3},
        },
    )
    assert patch_response.status_code == 200
    patched = patch_response.json()
    assert not patched["enabled"]
    assert patched["severity_override"] == "critical"
    assert patched["params"] == {"days_threshold": 3, "exclude_labels": []}

    reset_response = api_client.post("/api/signal-configs/stale-in-progress-work-item/reset")
    assert reset_response.status_code == 200
    reset = reset_response.json()
    assert reset["enabled"]
    assert reset["severity_override"] is None
    assert reset["params"] == {"days_threshold": 7, "exclude_labels": []}

    reset_all_response = api_client.post("/api/signal-configs/reset")
    assert reset_all_response.status_code == 200
    assert len(reset_all_response.json()) == 13


def test_signal_config_route_rejects_invalid_params(api_client: TestClient) -> None:
    response = api_client.patch(
        "/api/signal-configs/stale-in-progress-work-item",
        json={"params": {"days_threshold": -1}},
    )

    assert response.status_code == 422
