"""Testes de integração da API e do processamento de imagem."""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.app import create_app
from backend.config import PROJECT_ROOT, Settings
from backend.storage import ImageStorage

LOGO_RED = (220, 20, 60)


def make_logo(width: int = 400, height: int = 160) -> Image.Image:
    logo = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    logo.paste(LOGO_RED + (255,), (0, 0, width, height))
    # Cantinho transparente para garantir que o canal alpha é respeitado.
    transparent = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    logo.paste(transparent, (0, 0))
    return logo


def make_photo(size: tuple[int, int] = (1600, 1200), fmt: str = "JPEG", mode: str = "RGB") -> bytes:
    image = Image.new(mode, size, (90, 140, 200) if mode == "RGB" else (90, 140, 200, 255))
    if mode == "RGB":
        from PIL import ImageDraw

        ImageDraw.Draw(image).ellipse(
            [size[0] * 0.25, size[1] * 0.2, size[0] * 0.75, size[1] * 0.8],
            fill=(240, 200, 120),
        )
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    logo_path = tmp_path / "logo.png"
    make_logo().save(logo_path)
    return Settings(
        logo_path=logo_path,
        storage_dir=tmp_path / "storage",
        frontend_dir=PROJECT_ROOT / "frontend",
        cleanup_interval_seconds=3600,
        file_ttl_seconds=600,
    )


@pytest.fixture()
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_health_and_config(client: TestClient):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["logo_available"] is True

    config = client.get("/api/config").json()
    assert config["accepted_formats"] == ["image/jpeg", "image/png"]
    assert config["logo"]["available"] is True
    assert config["rules"]["position"] == "bottom-left"
    assert config["max_upload_mb"] > 0


def test_index_serves_frontend(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "FixLogo" in response.text

    assert client.get("/styles.css").status_code == 200
    assert client.get("/app.js").status_code == 200


def test_process_jpeg_returns_preview_and_download(client: TestClient, settings: Settings):
    response = client.post(
        "/api/process",
        files={"file": ("dog.jpg", make_photo(), "image/jpeg")},
    )
    assert response.status_code == 201, response.text
    payload = response.json()

    assert len(payload["id"]) == 32
    assert payload["download_name"] == "dog-logo.jpg"
    assert payload["media_type"] == "image/jpeg"
    assert payload["width"] == 1600 and payload["height"] == 1200
    assert payload["processing_ms"] >= 0

    preview = client.get(payload["preview_url"])
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(preview.content)).size[0] <= 1400

    download = client.get(payload["download_url"])
    assert download.status_code == 200
    assert "dog-logo.jpg" in download.headers["content-disposition"]

    result = Image.open(io.BytesIO(download.content)).convert("RGB")
    assert result.size == (1600, 1200)

    # A logo deve estar no canto inferior esquerdo.
    scaled_logo_width = round(1600 * settings.logo_width_ratio)
    padding = max(12, round(1200 * 0.025))
    pixel = result.getpixel((padding + scaled_logo_width // 2, 1200 - padding - 30))
    assert abs(pixel[0] - LOGO_RED[0]) < 20
    assert abs(pixel[1] - LOGO_RED[1]) < 20

    # O canto superior direito permanece com a cor original da foto.
    corner = result.getpixel((1550, 40))
    assert abs(corner[2] - 200) < 30


def test_process_png_keeps_png_format(client: TestClient):
    response = client.post(
        "/api/process",
        files={"file": ("cat.png", make_photo(fmt="PNG", mode="RGBA"), "image/png")},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["media_type"] == "image/png"
    assert payload["download_name"] == "cat-logo.png"

    download = client.get(payload["download_url"])
    assert download.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(download.content)).format == "PNG"


def test_rejects_unsupported_extension(client: TestClient):
    response = client.post(
        "/api/process",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415


def test_rejects_invalid_image_bytes(client: TestClient):
    response = client.post(
        "/api/process",
        files={"file": ("fake.png", b"not-an-image", "image/png")},
    )
    assert response.status_code == 400
    assert "imagem" in response.json()["detail"].lower()


def test_rejects_oversized_upload(tmp_path: Path):
    logo_path = tmp_path / "logo.png"
    make_logo().save(logo_path)
    config = Settings(
        logo_path=logo_path,
        storage_dir=tmp_path / "storage",
        max_upload_bytes=1024,
        cleanup_interval_seconds=3600,
    )
    with TestClient(create_app(config)) as client:
        response = client.post(
            "/api/process",
            files={"file": ("big.jpg", make_photo(), "image/jpeg")},
        )
    assert response.status_code == 413


def test_delete_and_expired_images(client: TestClient):
    payload = client.post(
        "/api/process",
        files={"file": ("pet.jpg", make_photo((800, 600)), "image/jpeg")},
    ).json()

    assert client.delete(f"/api/images/{payload['id']}").status_code == 204
    assert client.get(payload["download_url"]).status_code == 404
    assert client.get(payload["preview_url"]).status_code == 404


def test_invalid_ids_return_404(client: TestClient):
    assert client.get("/api/images/not-an-id/download").status_code == 404
    assert client.get("/api/images/" + "0" * 32 + "/preview").status_code == 404


def test_small_image_keeps_logo_inside_bounds(settings: Settings):
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/process",
            files={"file": ("tiny.jpg", make_photo((320, 240)), "image/jpeg")},
        )
        payload = response.json()

    assert response.status_code == 201
    assert payload["logo_width"] <= 320
    assert payload["logo_width"] >= settings.logo_min_width_px


def test_cleanup_removes_stale_files(tmp_path: Path):
    storage = ImageStorage(tmp_path / "storage")
    metadata = storage.save(
        final_image=b"final",
        preview_image=b"preview",
        original_name="foto.jpg",
        media_type="image/jpeg",
        extension=".jpg",
        width=100,
        height=100,
        logo_width=20,
        logo_height=20,
    )
    stale = time.time() - 7200

    # Simula arquivos com duas horas de idade.
    for path in storage.root.iterdir():
        os.utime(path, (stale, stale))

    removed = storage.cleanup(ttl_seconds=3600)
    assert removed == 3
    assert list(storage.root.iterdir()) == []


def test_missing_logo_returns_503(tmp_path: Path):
    config = Settings(
        logo_path=tmp_path / "does-not-exist.png",
        storage_dir=tmp_path / "storage",
        cleanup_interval_seconds=3600,
    )
    with TestClient(create_app(config)) as client:
        response = client.post(
            "/api/process",
            files={"file": ("pet.jpg", make_photo((800, 600)), "image/jpeg")},
        )
    assert response.status_code == 503
