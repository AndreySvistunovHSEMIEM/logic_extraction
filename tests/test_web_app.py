"""Тесты Flask web-приложения."""

import io
from unittest.mock import patch

import pytest

from web.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_health(client):
    """GET /api/health возвращает статус и модель."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "model" in data


def test_index(client):
    """GET / возвращает HTML-страницу."""
    resp = client.get("/")
    assert resp.status_code == 200


def test_upload_no_file(client):
    """POST /api/check без файла — 400."""
    resp = client.post("/api/check")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_upload_empty_filename(client):
    """POST /api/check с пустым именем файла — 400."""
    data = {"file": (io.BytesIO(b""), "")}
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_upload_unsupported_extension(client):
    """POST /api/check с неподдерживаемым расширением — 400."""
    data = {"file": (io.BytesIO(b"data"), "resume.docx")}
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "Unsupported" in resp.get_json()["error"]


def test_upload_success(client):
    """POST /api/check с валидным .txt — успех (mock pipeline)."""
    mock_report = {"summary": {"is_consistent": True}}
    with patch("web.app.run_pipeline", return_value=mock_report):
        data = {"file": (io.BytesIO(b"resume text"), "resume.txt")}
        resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    assert resp.get_json() == mock_report


def test_upload_pipeline_error(client):
    """POST /api/check при ошибке пайплайна — 500 с generic-сообщением."""
    with patch("web.app.run_pipeline", side_effect=RuntimeError("boom")):
        data = {"file": (io.BytesIO(b"resume text"), "resume.txt")}
        resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.status_code == 500
    assert resp.get_json()["error"] == "Internal server error"


def test_upload_file_too_large(client):
    """POST /api/check с файлом > 5 МБ — 400."""
    big_content = b"x" * (5 * 1024 * 1024 + 1)
    data = {"file": (io.BytesIO(big_content), "resume.txt")}
    resp = client.post("/api/check", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "too large" in resp.get_json()["error"]
