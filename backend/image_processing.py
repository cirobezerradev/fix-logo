"""Aplicação da logomarca sobre as fotos dos pets.

Toda a lógica de Pillow fica isolada aqui, de forma que o app web apenas
orquestre upload, validação e armazenamento.
"""

from __future__ import annotations

import io
import threading
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from .config import Settings, settings as default_settings

# Suporte a HEIC/HEIF (fotos padrão do iPhone) e AVIF. Se a dependência
# opcional não estiver instalada, a aplicação continua funcionando apenas
# com JPG/PNG.
try:
    from pillow_heif import register_heif_opener  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - depende do ambiente
    register_heif_opener = None  # type: ignore[assignment]

if register_heif_opener is not None:  # pragma: no cover - efeito colateral de import
    register_heif_opener()

# Formatos que o Pillow pode identificar e como devem ser gravados na saída.
# MPO é um JPEG com múltiplas imagens (HDR/Retrato do iPhone) e HEIC/HEIF é
# o formato padrão da câmera do iPhone.
SOURCE_FORMATS = {
    "JPEG": "JPEG",
    "MPO": "JPEG",
    "PNG": "PNG",
    "HEIF": "JPEG",
    "HEIC": "JPEG",
    "AVIF": "JPEG",
}

UNSUPPORTED_FORMAT_MESSAGE = "Formato não suportado. Envie imagens JPG, JPEG, PNG ou HEIC."


class InvalidImageError(ValueError):
    """Arquivo enviado não é uma imagem suportada (JPG, PNG, HEIC, MPO)."""


class LogoError(RuntimeError):
    """A logomarca não pôde ser carregada."""


@dataclass(frozen=True)
class ProcessResult:
    """Resultado do processamento de uma foto."""

    final_image: bytes
    media_type: str
    extension: str
    width: int
    height: int
    logo_width: int
    logo_height: int


class LogoCache:
    """Mantém a logo em memória e recarrega se o arquivo mudar no disco."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._signature: tuple[int, int] | None = None
        self._image: Image.Image | None = None

    def get(self) -> Image.Image:
        try:
            stat = self.path.stat()
        except FileNotFoundError as exc:
            raise LogoError(
                f"Logomarca não encontrada em '{self.path}'. "
                "Coloque o arquivo logo_petshop.png na pasta backend/logo/."
            ) from exc

        signature = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            if self._image is None or signature != self._signature:
                try:
                    with Image.open(self.path) as raw:
                        raw.load()
                        image = raw.convert("RGBA")
                except (OSError, UnidentifiedImageError) as exc:
                    raise LogoError(f"Não foi possível ler a logomarca '{self.path}'.") from exc
                self._image = image
                self._signature = signature
            return self._image.copy()

    def size(self) -> tuple[int, int]:
        image = self.get()
        return image.size


def load_uploaded_image(data: bytes, *, max_pixels: int) -> tuple[Image.Image, str]:
    """Abre os bytes enviados, valida o formato e corrige a orientação EXIF.

    Devolve a imagem já normalizada e o formato de saída ("JPEG" ou "PNG").
    Fotos HEIC/HEIF (iPhone) e MPO (HDR/Retrato) são convertidas para JPEG.
    """

    if not data:
        raise InvalidImageError("O arquivo enviado está vazio.")

    try:
        with Image.open(io.BytesIO(data)) as raw:
            raw_format = (raw.format or "").upper()
            output_format = SOURCE_FORMATS.get(raw_format)
            if output_format is None:
                raise InvalidImageError(UNSUPPORTED_FORMAT_MESSAGE)
            # Checa antes de descomprimir: protege a memória do servidor.
            if raw.width * raw.height > max_pixels:
                raise InvalidImageError(
                    f"A imagem tem {raw.width}×{raw.height} px, acima do limite de "
                    f"{max_pixels / 1_000_000:.0f} megapixels. Reduza a foto e tente novamente."
                )
            raw.load()
            image = ImageOps.exif_transpose(raw)
    except Image.DecompressionBombError as exc:  # type: ignore[attr-defined]
        raise InvalidImageError(
            "A imagem é grande demais para ser processada. Envie uma foto com menos de "
            f"{max_pixels / 1_000_000:.0f} megapixels."
        ) from exc
    except UnidentifiedImageError as exc:
        raise InvalidImageError(
            "Não foi possível ler a imagem. Se for uma foto do iPhone no formato HEIC, "
            "instale o suporte a HEIC no servidor (pillow-heif) ou converta para JPEG."
        ) from exc
    except OSError as exc:
        raise InvalidImageError("Não foi possível abrir a imagem enviada.") from exc

    if image.width < 16 or image.height < 16:
        raise InvalidImageError("A imagem é pequena demais para receber a logomarca.")
    return image, output_format


def _scale_alpha(logo: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 1.0:
        return logo
    scaled = logo.copy()
    alpha = scaled.getchannel("A").point(lambda value: int(value * max(0.0, opacity)))
    scaled.putalpha(alpha)
    return scaled


def _resize_logo(logo: Image.Image, target_width: int, max_height: int) -> Image.Image:
    target_width = max(1, target_width)
    ratio = target_width / logo.width
    target_height = max(1, round(logo.height * ratio))
    if target_height > max_height:
        target_height = max(1, max_height)
        target_width = max(1, round(logo.width * (target_height / logo.height)))
    if (target_width, target_height) == logo.size:
        return logo
    return logo.resize((target_width, target_height), Image.Resampling.LANCZOS)


def apply_logo(
    image: Image.Image,
    logo: Image.Image,
    *,
    source_format: str = "JPEG",
    config: Settings = default_settings,
) -> ProcessResult:
    """Sobrepõe a logo no canto inferior esquerdo e devolve os bytes finais."""

    width, height = image.size
    is_png = source_format == "PNG"

    # Margem proporcional ao menor lado, com piso e teto para fotos extremas.
    padding = max(
        config.logo_padding_min_px,
        round(min(width, height) * config.logo_padding_ratio),
    )
    padding = max(1, min(padding, min(width, height) // 4))

    max_logo_w = max(1, width - 2 * padding)
    max_logo_h = max(1, height - 2 * padding)

    target_w = round(width * config.logo_width_ratio)
    target_w = max(target_w, round(width * config.logo_min_width_ratio))
    target_w = min(target_w, round(width * config.logo_max_width_ratio))
    target_w = max(target_w, min(config.logo_min_width_px, max_logo_w))
    target_w = min(target_w, max_logo_w)

    resized_logo = _resize_logo(_scale_alpha(logo, config.logo_opacity), target_w, max_logo_h)

    position = (padding, height - padding - resized_logo.height)

    # JPEG não tem canal alpha: compor direto no RGB evita uma cópia RGBA
    # inteira da foto, o que reduz bastante o pico de memória.
    if is_png:
        base = image.convert("RGBA")
        base.alpha_composite(resized_logo, dest=position)
        final_image = base
    else:
        final_image = image if image.mode == "RGB" else image.convert("RGB")
        final_image.paste(resized_logo, position, resized_logo.getchannel("A"))

    out = io.BytesIO()
    if is_png:
        final_image.save(out, format="PNG", compress_level=config.png_compress_level)
        extension, media_type = ".png", "image/png"
    else:
        final_image.save(out, format="JPEG", quality=config.jpeg_quality, progressive=True)
        extension, media_type = ".jpg", "image/jpeg"

    return ProcessResult(
        final_image=out.getvalue(),
        media_type=media_type,
        extension=extension,
        width=width,
        height=height,
        logo_width=resized_logo.width,
        logo_height=resized_logo.height,
    )
