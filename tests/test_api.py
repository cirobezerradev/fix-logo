"""Testes de integração da API (envio em lote, sem pré-visualização)."""

from __future__ import annotations

import io
import os
import time
import warnings
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

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
        ImageDraw.Draw(image).ellipse(
            [size[0] * 0.25, size[1] * 0.2, size[0] * 0.75, size[1] * 0.8],
            fill=(240, 200, 120),
        )
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def upload_part(name: str, data: bytes, content_type: str = "image/jpeg") -> tuple[str, tuple[str, bytes, str]]:
    return ("files", (name, data, content_type))


def jpeg_part(name: str = "dog.jpg", size: tuple[int, int] = (1600, 1200)):
    return upload_part(name, make_photo(size), "image/jpeg")


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


def test_health_and_config(client: TestClient, settings: Settings):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["logo_available"] is True

    config = client.get("/api/config").json()
    assert config["accepted_formats"] == ["image/jpeg", "image/png"]
    assert config["logo"]["available"] is True
    assert config["rules"]["position"] == "bottom-left"
    assert config["max_batch_files"] == settings.max_batch_files
    assert config["max_upload_mb"] > 0


def test_index_serves_frontend(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "FixLogo" in response.text

    assert client.get("/styles.css").status_code == 200
    assert client.get("/app.js").status_code == 200


def test_single_photo_returns_individual_download(client: TestClient, settings: Settings):
    response = client.post("/api/process", files=[jpeg_part()])
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["total"] == 1
    assert payload["succeeded"] == 1
    assert payload["failed"] == 0

    item = payload["items"][0]
    assert item["ok"] is True
    assert item["download_name"] == "dog-logo.jpg"
    assert item["media_type"] == "image/jpeg"
    assert item["width"] == 1600 and item["height"] == 1200
    assert item["download_url"] == f"/api/images/{item['id']}/download"
    # Não há pré-visualização: nem URL na resposta, nem rota no backend.
    assert "preview_url" not in item
    assert client.get(f"/api/images/{item['id']}/preview").status_code == 404

    download = client.get(item["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "image/jpeg"
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


def test_png_keeps_png_format(client: TestClient):
    png = make_photo(fmt="PNG", mode="RGBA")
    response = client.post("/api/process", files=[upload_part("cat.png", png, "image/png")])
    assert response.status_code == 200, response.text

    item = response.json()["items"][0]
    assert item["media_type"] == "image/png"
    assert item["download_name"] == "cat-logo.png"

    download = client.get(item["download_url"])
    assert download.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(download.content)).format == "PNG"


def test_batch_returns_one_download_link_per_photo(client: TestClient):
    png = make_photo((900, 700), fmt="PNG", mode="RGBA")
    response = client.post(
        "/api/process",
        files=[
            jpeg_part("a.jpg", (800, 600)),
            upload_part("b.png", png, "image/png"),
            upload_part("c.txt", b"nao-e-foto", "text/plain"),
        ],
    )
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["total"] == 3
    assert payload["succeeded"] == 2
    assert payload["failed"] == 1

    items = payload["items"]
    assert [item["original_name"] for item in items] == ["a.jpg", "b.png", "c.txt"]
    assert items[0]["ok"] and items[1]["ok"]
    assert items[2]["ok"] is False
    assert "Formato" in items[2]["error"]
    assert items[0]["download_url"] != items[1]["download_url"]

    for item in items[:2]:
        download = client.get(item["download_url"])
        assert download.status_code == 200
        assert download.headers["content-type"] == item["media_type"]


def test_invalid_photo_does_not_interrupt_batch(client: TestClient):
    response = client.post(
        "/api/process",
        files=[
            upload_part("quebrada.png", b"not-an-image", "image/png"),
            jpeg_part("ok.jpg", (800, 600)),
        ],
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["succeeded"] == 1
    assert payload["failed"] == 1
    assert payload["items"][0]["ok"] is False
    assert "imagem" in payload["items"][0]["error"].lower()
    assert payload["items"][1]["ok"] is True


def test_batch_size_limit(tmp_path: Path):
    logo_path = tmp_path / "logo.png"
    make_logo().save(logo_path)
    config = Settings(
        logo_path=logo_path,
        storage_dir=tmp_path / "storage",
        max_batch_files=2,
        cleanup_interval_seconds=3600,
    )
    with TestClient(create_app(config)) as client:
        response = client.post(
            "/api/process",
            files=[jpeg_part(f"{index}.jpg", (320, 240)) for index in range(3)],
        )
    assert response.status_code == 413
    assert "2" in response.json()["detail"]


def test_rejects_oversized_upload_as_item_error(tmp_path: Path):
    logo_path = tmp_path / "logo.png"
    make_logo().save(logo_path)
    config = Settings(
        logo_path=logo_path,
        storage_dir=tmp_path / "storage",
        max_upload_bytes=1024,
        cleanup_interval_seconds=3600,
    )
    with TestClient(create_app(config)) as client:
        response = client.post("/api/process", files=[jpeg_part("big.jpg", (800, 600))])
    assert response.status_code == 200
    assert response.json()["failed"] == 1
    assert "MB" in response.json()["items"][0]["error"]


def test_rejects_too_many_pixels_as_item_error(tmp_path: Path):
    logo_path = tmp_path / "logo.png"
    make_logo().save(logo_path)
    # 800x600 = 480 mil pixels, acima do limite de 300 mil.
    config = Settings(
        logo_path=logo_path,
        storage_dir=tmp_path / "storage",
        max_image_pixels=300_000,
        cleanup_interval_seconds=3600,
    )
    with TestClient(create_app(config)) as client:
        with warnings.catch_warnings():
            # O Pillow avisa antes do nosso limite; aqui o erro esperado é o item inválido.
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            response = client.post("/api/process", files=[jpeg_part("grande.jpg", (800, 600))])

    assert response.status_code == 200
    assert response.json()["failed"] == 1
    assert "megapixels" in response.json()["items"][0]["error"].lower()


def test_delete_and_expired_images(client: TestClient):
    payload = client.post("/api/process", files=[jpeg_part("pet.jpg", (800, 600))]).json()
    item = payload["items"][0]

    assert client.delete(f"/api/images/{item['id']}").status_code == 204
    assert client.get(item["download_url"]).status_code == 404


def test_invalid_ids_return_404(client: TestClient):
    assert client.get("/api/images/not-an-id/download").status_code == 404
    assert client.get("/api/images/" + "0" * 32 + "/download").status_code == 404


def test_small_image_keeps_logo_inside_bounds(settings: Settings):
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/process", files=[jpeg_part("tiny.jpg", (320, 240))])

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["logo_width"] <= 320
    assert item["logo_width"] >= settings.logo_min_width_px


def test_cleanup_removes_stale_files(tmp_path: Path):
    storage = ImageStorage(tmp_path / "storage")
    storage.save(
        final_image=b"final",
        original_name="foto.jpg",
        media_type="image/jpeg",
        extension=".jpg",
        width=100,
        height=100,
        logo_width=20,
        logo_height=20,
    )

    # Cada foto gera apenas a imagem final + metadados.
    assert len(list(storage.root.iterdir())) == 2

    stale = time.time() - 7200
    for path in storage.root.iterdir():
        os.utime(path, (stale, stale))

    removed = storage.cleanup(ttl_seconds=3600)
    assert removed == 2
    assert list(storage.root.iterdir()) == []


def test_missing_logo_returns_503(tmp_path: Path):
    config = Settings(
        logo_path=tmp_path / "does-not-exist.png",
        storage_dir=tmp_path / "storage",
        cleanup_interval_seconds=3600,
    )
    with TestClient(create_app(config)) as client:
        response = client.post("/api/process", files=[jpeg_part("pet.jpg", (800, 600))])
    assert response.status_code == 503
