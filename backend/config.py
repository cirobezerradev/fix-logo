"""Configurações da aplicação.

Todos os valores podem ser sobrescritos por variáveis de ambiente, o que
facilita o ajuste fino da marca d'água sem mexer no código.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Parâmetros de processamento e de infraestrutura."""

    # --- Caminhos -----------------------------------------------------
    logo_path: Path = field(default_factory=lambda: _env_path("LOGO_PATH", BASE_DIR / "logo" / "logo_petshop.png"))
    storage_dir: Path = field(default_factory=lambda: _env_path("STORAGE_DIR", BASE_DIR / "storage"))
    frontend_dir: Path = field(default_factory=lambda: _env_path("FRONTEND_DIR", PROJECT_ROOT / "frontend"))

    # --- Limites de upload --------------------------------------------
    max_upload_bytes: int = field(default_factory=lambda: _env_int("MAX_UPLOAD_BYTES", 25 * 1024 * 1024))
    max_batch_files: int = field(default_factory=lambda: _env_int("MAX_BATCH_FILES", 20))
    max_batch_bytes: int = field(default_factory=lambda: _env_int("MAX_BATCH_BYTES", 120 * 1024 * 1024))
    max_image_pixels: int = field(default_factory=lambda: _env_int("MAX_IMAGE_PIXELS", 60_000_000))
    allowed_formats: tuple[str, ...] = ("JPEG", "MPO", "PNG", "HEIF", "AVIF")
    allowed_extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".heic", ".heif")

    # --- Regra de sobreposição da logo --------------------------------
    # Largura da logo como fração da largura da foto (22,5% por padrão).
    logo_width_ratio: float = field(default_factory=lambda: _env_float("LOGO_WIDTH_RATIO", 0.225))
    # Limites de segurança para fotos muito pequenas ou muito largas.
    logo_min_width_ratio: float = field(default_factory=lambda: _env_float("LOGO_MIN_WIDTH_RATIO", 0.10))
    logo_max_width_ratio: float = field(default_factory=lambda: _env_float("LOGO_MAX_WIDTH_RATIO", 0.40))
    logo_min_width_px: int = field(default_factory=lambda: _env_int("LOGO_MIN_WIDTH_PX", 48))
    # Margem em relação ao menor lado da foto (2.5% por padrão).
    logo_padding_ratio: float = field(default_factory=lambda: _env_float("LOGO_PADDING_RATIO", 0.025))
    logo_padding_min_px: int = field(default_factory=lambda: _env_int("LOGO_PADDING_MIN_PX", 12))
    logo_opacity: float = field(default_factory=lambda: _env_float("LOGO_OPACITY", 1.0))

    # --- Qualidade de saída -------------------------------------------
    jpeg_quality: int = field(default_factory=lambda: _env_int("JPEG_QUALITY", 92))
    png_compress_level: int = field(default_factory=lambda: _env_int("PNG_COMPRESS_LEVEL", 6))

    # --- Limpeza automática -------------------------------------------
    file_ttl_seconds: int = field(default_factory=lambda: _env_int("FILE_TTL_SECONDS", 3600))
    cleanup_interval_seconds: int = field(default_factory=lambda: _env_int("CLEANUP_INTERVAL_SECONDS", 900))

    @property
    def max_upload_mb(self) -> float:
        return round(self.max_upload_bytes / (1024 * 1024), 1)


settings = Settings()
