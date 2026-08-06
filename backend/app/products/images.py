"""Fotos de produto: gravação em disco e limpeza.

Arquivo em disco e não base64 no banco: a tela de contagem do promotor carrega
o catálogo inteiro de uma vez, e uma foto embutida em cada linha do JSON deixaria
esse carregamento inviável no 3G de um supermercado. Em disco, a foto é uma URL
que o navegador (e o service worker) cacheia sozinho.

O diretório vive dentro de `backend/`, que o docker-compose monta do host — logo
as fotos sobrevivem a `docker compose down`.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

from fastapi import HTTPException

logger = logging.getLogger(__name__)

UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads"
PRODUCTS_DIR = UPLOAD_ROOT / "products"
PUBLIC_PREFIX = "/uploads/products"

MAX_BYTES = 8 * 1024 * 1024   # foto de celular moderno cabe folgado
MAX_SIDE = 1200               # o promotor olha num celular; 1200px já é de sobra

_ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/pjpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def ensure_dirs() -> None:
    PRODUCTS_DIR.mkdir(parents=True, exist_ok=True)


def save_product_image(product_id: UUID, raw: bytes, content_type: Optional[str]) -> str:
    """Grava a foto e devolve a URL pública relativa."""
    extension = _ALLOWED_TYPES.get((content_type or "").lower())
    if not extension:
        raise HTTPException(
            status_code=415,
            detail="Formato não suportado. Envie uma imagem JPG, PNG ou WEBP.",
        )
    if not raw:
        raise HTTPException(status_code=422, detail="Arquivo vazio")
    if len(raw) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Imagem muito grande (máximo {MAX_BYTES // (1024 * 1024)} MB)",
        )

    content, compressed_extension = _compress(raw)
    if compressed_extension:
        extension = compressed_extension

    ensure_dirs()
    # Sufixo aleatório em vez do id puro: trocar a foto muda a URL e o navegador
    # não fica exibindo a antiga do cache.
    filename = f"{product_id}-{uuid4().hex[:8]}{extension}"
    (PRODUCTS_DIR / filename).write_bytes(content)
    return f"{PUBLIC_PREFIX}/{filename}"


def delete_product_image(image_url: Optional[str]) -> None:
    """Apaga o arquivo de uma URL gravada antes. Silencioso: foto órfã em disco
    é irrelevante, mas quebrar o salvamento do produto por causa dela não é."""
    if not image_url or not image_url.startswith(f"{PUBLIC_PREFIX}/"):
        return
    filename = Path(image_url).name
    try:
        (PRODUCTS_DIR / filename).unlink(missing_ok=True)
    except OSError:
        logger.warning("Não foi possível apagar a foto %s", filename)


def _compress(raw: bytes) -> tuple[bytes, str]:
    """Reduz a foto a `MAX_SIDE` e reconverte para JPEG.

    Sem Pillow instalado devolve o original: a tela funciona igual, só pesa mais.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        logger.info("Pillow não instalado — gravando a foto sem redimensionar")
        return raw, ""

    import io

    try:
        with Image.open(io.BytesIO(raw)) as image:
            # Respeita a orientação EXIF, senão foto de celular vem deitada
            image = ImageOps.exif_transpose(image)
            image.thumbnail((MAX_SIDE, MAX_SIDE))

            if image.mode in ("RGBA", "LA", "P"):
                # JPEG não tem transparência — achata sobre branco
                background = Image.new("RGB", image.size, (255, 255, 255))
                converted = image.convert("RGBA")
                background.paste(converted, mask=converted.split()[-1])
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")

            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=85, optimize=True)
            return buffer.getvalue(), ".jpg"
    except Exception:
        logger.exception("Falha ao processar a imagem — gravando o original")
        return raw, ""
