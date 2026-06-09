from pathlib import Path

from fastapi.testclient import TestClient

from em_radar_api.main import app, create_app


def test_health() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_static_ui_and_client_side_routes(tmp_path: Path) -> None:
    index = "<html><body>EM Radar</body></html>"
    (tmp_path / "index.html").write_text(index)

    client = TestClient(create_app(static_dir=tmp_path))

    assert client.get("/").text == index
    assert client.get("/teams").text == index
    assert client.get("/apiary").text == index


def test_unknown_api_route_does_not_return_static_ui(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html><body>EM Radar</body></html>")

    response = TestClient(create_app(static_dir=tmp_path)).get("/api/unknown")

    assert response.status_code == 404
    assert "EM Radar" not in response.text
