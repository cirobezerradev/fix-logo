"""Armazenamento temporário das imagens processadas.

Cada imagem gera dois arquivos na pasta de storage:

* ``<id>.<ext>``          -> imagem final em alta qualidade (download)
* ``<id>.json``           -> metadados (nome original, tipo, dimensões...)

A aplicação não gera pré-visualizações: o resultado é servido apenas pelo
endpoint de download individual. Nada é persistido em banco de dados: o
storage é descartável e limpo periodicamente conforme o TTL configurado.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
METADATA_SUFFIX = ".json"


@dataclass(frozen=True)
class ImageMetadata:
    id: str
    original_name: str
    download_name: str
    media_type: str
    extension: str
    width: int
    height: int
    logo_width: int
    logo_height: int
    created_at: float


def is_valid_id(image_id: str) -> bool:
    return bool(ID_PATTERN.fullmatch(image_id))


class ImageStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------
    def ensure_ready(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        *,
        final_image: bytes,
        original_name: str,
        media_type: str,
        extension: str,
        width: int,
        height: int,
        logo_width: int,
        logo_height: int,
    ) -> ImageMetadata:
        self.ensure_ready()
        image_id = uuid.uuid4().hex
        download_name = self._build_download_name(original_name, extension)

        metadata = ImageMetadata(
            id=image_id,
            original_name=original_name,
            download_name=download_name,
            media_type=media_type,
            extension=extension,
            width=width,
            height=height,
            logo_width=logo_width,
            logo_height=logo_height,
            created_at=time.time(),
        )

        # Escreve primeiro em arquivos temporários para evitar servir
        # resultados incompletos em caso de falha no meio do caminho.
        final_path = self.root / f"{image_id}{extension}"
        final_tmp = self.root / f"{image_id}{extension}.tmp"
        meta_tmp = self.root / f"{image_id}{METADATA_SUFFIX}.tmp"

        final_tmp.write_bytes(final_image)
        meta_tmp.write_text(json.dumps(asdict(metadata), ensure_ascii=False), encoding="utf-8")

        final_tmp.replace(final_path)
        meta_tmp.replace(self.metadata_path(image_id))
        return metadata

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------
    def metadata(self, image_id: str) -> ImageMetadata | None:
        if not is_valid_id(image_id):
            return None
        try:
            raw: dict[str, Any] = json.loads(self.metadata_path(image_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        try:
            return ImageMetadata(**raw)
        except TypeError:
            return None

    def final_path(self, image_id: str) -> Path:
        metadata = self.metadata(image_id)
        extension = metadata.extension if metadata else ".jpg"
        return self.root / f"{image_id}{extension}"

    def metadata_path(self, image_id: str) -> Path:
        return self.root / f"{image_id}{METADATA_SUFFIX}"

    def resolve_final(self, image_id: str) -> tuple[Path, ImageMetadata] | None:
        """Devolve o caminho da imagem final somente se todos os arquivos existirem."""
        metadata = self.metadata(image_id)
        if metadata is None:
            return None
        final = self.final_path(image_id)
        if not final.is_file():
            return None
        return final, metadata

    # ------------------------------------------------------------------
    # Exclusão / limpeza
    # ------------------------------------------------------------------
    def delete(self, image_id: str) -> bool:
        if not is_valid_id(image_id):
            return False
        removed = False
        # O metadata é removido por último: ele guarda a extensão real do arquivo.
        for path in sorted(
            self.root.glob(f"{image_id}.*"),
            key=lambda item: item.suffix == METADATA_SUFFIX,
        ):
            try:
                path.unlink()
                removed = True
            except FileNotFoundError:
                continue
            except OSError:
                continue
        return removed

    def cleanup(self, ttl_seconds: int, *, now: float | None = None) -> int:
        """Remove arquivos mais antigos que o TTL e órfãos. Devolve quantos removeu."""
        if not self.root.is_dir():
            return 0

        reference = now if now is not None else time.time()
        cutoff = reference - ttl_seconds
        removed = 0
        metadata_ids: set[str] = set()

        for entry in self.root.iterdir():
            if not entry.is_file():
                continue
            try:
                stale = entry.stat().st_mtime < cutoff
            except OSError:
                continue
            if stale or entry.suffix == ".tmp":
                try:
                    entry.unlink()
                    removed += 1
                except OSError:
                    pass
                continue
            if entry.suffix == METADATA_SUFFIX:
                metadata_ids.add(entry.stem)

        # Remove prévias/finais que perderam o metadata correspondente.
        for entry in self.root.iterdir():
            if not entry.is_file() or entry.suffix in {METADATA_SUFFIX, ".tmp"}:
                continue
            candidate_id = entry.name.split(".", 1)[0]
            if candidate_id not in metadata_ids:
                try:
                    entry.unlink()
                    removed += 1
                except OSError:
                    pass

        return removed

    @staticmethod
    def _build_download_name(original_name: str, extension: str) -> str:
        stem = Path(original_name or "foto").stem
        stem = re.sub(r"[^\w\-. ]+", "", stem, flags=re.UNICODE).strip(" .")
        stem = re.sub(r"\s+", "-", stem)[:60] or "foto"
        return f"{stem}-logo{extension}"
