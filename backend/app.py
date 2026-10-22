"""FixLogo - API FastAPI.

Execução (a partir da raiz do projeto):

    uvicorn backend.app:app --reload

A API também serve o frontend estático em ``/``, então basta abrir
http://127.0.0.1:8000 no navegador.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image

from .config import Settings, settings
from .image_processing import (
    InvalidImageError,
    LogoCache,
    LogoError,
    apply_logo,
    load_uploaded_image,
)
from .storage import ImageStorage, is_valid_id

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("petshop.watermark")

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "application/octet-stream"}


async def _cleanup_loop(storage: ImageStorage, config: Settings) -> None:
    """Remove imagens antigas periodicamente (RF05)."""
    while True:
        await asyncio.sleep(config.cleanup_interval_seconds)
        try:
            removed = await asyncio.to_thread(storage.cleanup, config.file_ttl_seconds)
            if removed:
                logger.info("Limpeza automática removeu %s arquivo(s) temporário(s).", removed)
        except Exception:  # pragma: no cover - falha de disco não deve derrubar a API
            logger.exception("Falha na limpeza automática do storage.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config: Settings = app.state.settings
    storage: ImageStorage = app.state.storage

    storage.ensure_ready()
    Image.MAX_IMAGE_PIXELS = config.max_image_pixels

    try:
        width, height = app.state.logo_cache.size()
        logger.info("Logomarca carregada (%sx%s) de %s", width, height, config.logo_path)
    except LogoError as exc:
        logger.warning("%s", exc)

    with suppress(Exception):
        removed = await asyncio.to_thread(storage.cleanup, config.file_ttl_seconds)
        if removed:
            logger.info("Limpeza inicial removeu %s arquivo(s).", removed)

    cleanup_task = asyncio.create_task(_cleanup_loop(storage, config))
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


def create_app(config: Settings | None = None) -> FastAPI:
    config = config or settings

    app = FastAPI(
        title="FixLogo",
        description="Aplica automaticamente a logomarca do petshop nas fotos dos pets.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.storage = ImageStorage(config.storage_dir)
    app.state.logo_cache = LogoCache(config.logo_path)

    origins = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time"] = f"{(time.perf_counter() - started) * 1000:.1f}ms"
        return response

    def get_config(request: Request) -> Settings:
        return request.app.state.settings

    def get_storage(request: Request) -> ImageStorage:
        return request.app.state.storage

    # ------------------------------------------------------------------
    # Frontend estático
    # ------------------------------------------------------------------
    def _static_file(name: str, media_type: str) -> FileResponse:
        path = config.frontend_dir / name
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"'{name}' não encontrado.")
        return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-cache"})

    @app.get("/", include_in_schema=False)
    async def index():
        index_file = config.frontend_dir / "index.html"
        if not index_file.is_file():
            return JSONResponse(
                status_code=404,
                content={"detail": f"Frontend não encontrado em '{config.frontend_dir}'."},
            )
        return FileResponse(index_file, media_type="text/html", headers={"Cache-Control": "no-cache"})

    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon():
        icon = config.frontend_dir / "favicon.svg"
        if not icon.is_file():
            raise HTTPException(status_code=404, detail="Favicon não encontrado.")
        return FileResponse(icon, media_type="image/svg+xml")

    @app.get("/styles.css", include_in_schema=False)
    async def styles():
        return _static_file("styles.css", "text/css")

    @app.get("/app.js", include_in_schema=False)
    async def script():
        return _static_file("app.js", "text/javascript")

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    @app.get("/api/health")
    async def health(
        config: Settings = Depends(get_config),
        storage: ImageStorage = Depends(get_storage),
    ):
        return {
            "status": "ok",
            "logo_available": config.logo_path.is_file(),
            "storage_ready": storage.root.is_dir(),
        }

    @app.get("/api/config")
    async def public_config(
        request: Request,
        config: Settings = Depends(get_config),
    ):
        logo_info: dict[str, object] = {"available": config.logo_path.is_file(), "width": None, "height": None}
        if logo_info["available"]:
            try:
                width, height = request.app.state.logo_cache.size()
                logo_info["width"], logo_info["height"] = width, height
            except LogoError:
                logo_info["available"] = False

        return {
            "max_upload_mb": config.max_upload_mb,
            "max_batch_files": config.max_batch_files,
            "max_batch_mb": round(config.max_batch_bytes / (1024 * 1024), 1),
            "accepted_formats": ["image/jpeg", "image/png"],
            "accepted_extensions": list(config.allowed_extensions),
            "logo": logo_info,
            "rules": {
                "logo_width_percent": round(config.logo_width_ratio * 100, 1),
                "padding_percent": round(config.logo_padding_ratio * 100, 1),
                "position": "bottom-left",
            },
            "file_ttl_minutes": round(config.file_ttl_seconds / 60),
        }

    @app.post("/api/process")
    async def process_images(
        request: Request,
        files: list[UploadFile] = File(
            ...,
            description="Uma ou mais fotos do pet em JPG, JPEG ou PNG (campo repetido 'files')",
        ),
        config: Settings = Depends(get_config),
        storage: ImageStorage = Depends(get_storage),
    ):
        """Processa um lote de fotos e devolve um link de download por foto.

        Os erros são individualizados: uma foto inválida não impede que as
        demais sejam processadas.
        """
        started = time.perf_counter()

        if not config.logo_path.is_file():
            raise HTTPException(
                status_code=503,
                detail=(
                    "A logomarca do petshop não está configurada. "
                    "Adicione o arquivo backend/logo/logo_petshop.png."
                ),
            )

        if not files:
            raise HTTPException(status_code=400, detail="Nenhuma foto foi enviada.")

        if len(files) > config.max_batch_files:
            raise HTTPException(
                status_code=413,
                detail=f"Envie no máximo {config.max_batch_files} fotos por vez.",
            )

        reported_sizes = [upload.size for upload in files if upload.size]
        if reported_sizes and sum(reported_sizes) > config.max_batch_bytes:
            limit_mb = config.max_batch_bytes / (1024 * 1024)
            raise HTTPException(
                status_code=413,
                detail=f"O lote passa de {limit_mb:.0f} MB. Envie menos fotos por vez.",
            )

        try:
            logo = request.app.state.logo_cache.get()
        except LogoError as exc:
            logger.error("Logo indisponível: %s", exc)
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        items = [
            await _process_one(upload, logo=logo, config=config, storage=storage)
            for upload in files
        ]

        succeeded = sum(1 for item in items if item["ok"])
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        logger.info(
            "Lote de %s foto(s): %s ok, %s com erro em %sms",
            len(items),
            succeeded,
            len(items) - succeeded,
            elapsed_ms,
        )

        return {
            "total": len(items),
            "succeeded": succeeded,
            "failed": len(items) - succeeded,
            "expires_in_minutes": round(config.file_ttl_seconds / 60),
            "processing_ms": elapsed_ms,
            "items": items,
        }

    @app.get("/api/images/{image_id}/download", name="download_image")
    async def download_image(
        image_id: str,
        storage: ImageStorage = Depends(get_storage),
    ):
        resolved = storage.resolve_final(image_id)
        if resolved is None:
            raise HTTPException(status_code=404, detail="Imagem expirada ou inexistente.")
        path, metadata = resolved
        return FileResponse(
            path,
            media_type=metadata.media_type,
            filename=metadata.download_name,
            headers={"Cache-Control": "no-store"},
        )

    @app.delete("/api/images/{image_id}", status_code=204)
    async def delete_image(
        image_id: str,
        storage: ImageStorage = Depends(get_storage),
    ):
        if not is_valid_id(image_id) or not storage.delete(image_id):
            raise HTTPException(status_code=404, detail="Imagem inexistente.")
        return Response(status_code=204)

    return app


async def _process_one(
    upload: UploadFile,
    *,
    logo: Image.Image,
    config: Settings,
    storage: ImageStorage,
) -> dict[str, object]:
    """Processa uma foto do lote e devolve o resultado individual."""
    filename = (upload.filename or "").strip() or "foto"
    started = time.perf_counter()

    try:
        suffix = Path(filename).suffix.lower()
        if suffix and suffix not in config.allowed_extensions:
            raise HTTPException(
                status_code=415,
                detail="Formato não suportado. Envie imagens JPG, JPEG ou PNG.",
            )

        content_type = (upload.content_type or "").lower()
        if content_type and content_type not in ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=415,
                detail="Formato não suportado. Envie imagens JPG, JPEG ou PNG.",
            )

        data = await _read_limited(upload, config.max_upload_bytes)

        try:
            image, source_format = load_uploaded_image(data, max_pixels=config.max_image_pixels)
            result = await asyncio.to_thread(
                apply_logo, image, logo, source_format=source_format, config=config
            )
        except InvalidImageError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        metadata = await asyncio.to_thread(
            storage.save,
            final_image=result.final_image,
            original_name=filename,
            media_type=result.media_type,
            extension=result.extension,
            width=result.width,
            height=result.height,
            logo_width=result.logo_width,
            logo_height=result.logo_height,
        )

        elapsed_ms = round((time.perf_counter() - started) * 1000)
        logger.info(
            "Imagem %s processada em %sms (%sx%s -> logo %sx%s)",
            metadata.id,
            elapsed_ms,
            metadata.width,
            metadata.height,
            metadata.logo_width,
            metadata.logo_height,
        )

        return {
            "ok": True,
            "id": metadata.id,
            "original_name": metadata.original_name,
            "download_name": metadata.download_name,
            "media_type": metadata.media_type,
            "width": metadata.width,
            "height": metadata.height,
            "logo_width": metadata.logo_width,
            "logo_height": metadata.logo_height,
            "download_url": f"/api/images/{metadata.id}/download",
            "processing_ms": elapsed_ms,
        }
    except HTTPException as exc:
        logger.warning("Foto '%s' recusada: %s", filename, exc.detail)
        return {"ok": False, "original_name": filename, "error": str(exc.detail)}
    except Exception:
        logger.exception("Falha ao processar a foto '%s'.", filename)
        return {
            "ok": False,
            "original_name": filename,
            "error": "Não foi possível processar esta imagem. Tente novamente.",
        }
    finally:
        await upload.close()


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    """Lê o upload em blocos respeitando o limite de tamanho."""
    chunk_size = 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"Arquivo muito grande. O limite é de {limit / (1024 * 1024):.0f} MB.",
            )
        chunks.append(chunk)
    if total == 0:
        raise HTTPException(status_code=400, detail="Nenhum arquivo foi enviado.")
    return b"".join(chunks)


app = create_app()
