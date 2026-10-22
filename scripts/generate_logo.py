"""Gera uma logomarca provisória com transparência (PNG).

Use este script apenas enquanto a logo oficial do petshop não estiver
disponível. Basta substituir o arquivo gerado por
``backend/logo/logo_petshop.png`` pela arte real (com canal alpha).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUTPUT = Path(__file__).resolve().parents[1] / "backend" / "logo" / "logo_petshop.png"

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def draw_paw(draw: ImageDraw.ImageDraw, center: tuple[float, float], scale: float, color: str) -> None:
    cx, cy = center
    # Almofada principal
    draw.ellipse(
        [cx - 0.30 * scale, cy + 0.02 * scale, cx + 0.30 * scale, cy + 0.42 * scale],
        fill=color,
    )
    # Dedinhos
    pads = [
        (cx - 0.34 * scale, cy - 0.16 * scale, 0.13 * scale),
        (cx - 0.13 * scale, cy - 0.30 * scale, 0.14 * scale),
        (cx + 0.12 * scale, cy - 0.30 * scale, 0.14 * scale),
        (cx + 0.34 * scale, cy - 0.16 * scale, 0.13 * scale),
    ]
    for px, py, radius in pads:
        draw.ellipse([px - radius, py - radius, px + radius, py + radius], fill=color)


def build_logo(width: int = 960, height: int = 320) -> Image.Image:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Selo com gradiente vertical (teal -> emerald)
    badge = 260
    badge_top = (height - badge) // 2
    badge_mask = Image.new("L", (badge, badge), 0)
    ImageDraw.Draw(badge_mask).rounded_rectangle([0, 0, badge, badge], radius=78, fill=255)

    gradient = Image.new("RGBA", (badge, badge))
    grad_draw = ImageDraw.Draw(gradient)
    start = (20, 184, 166)
    end = (16, 185, 129)
    for y in range(badge):
        t = y / (badge - 1)
        color = tuple(round(start[i] + (end[i] - start[i]) * t) for i in range(3)) + (255,)
        grad_draw.line([(0, y), (badge, y)], fill=color)

    image.paste(gradient, (26, badge_top), badge_mask)

    draw = ImageDraw.Draw(image)
    draw_paw(draw, (26 + badge / 2, badge_top + badge / 2 - 12), badge * 0.72, "white")

    # Nome do petshop
    title_font = load_font(118)
    draw.text((26 + badge + 34, 46), "PetShop", font=title_font, fill=(15, 23, 42, 255))

    # Assinatura
    subtitle_font = load_font(36)
    draw.text(
        (26 + badge + 40, 196),
        "BANHO & TOSA",
        font=subtitle_font,
        fill=(13, 148, 136, 255),
    )

    # Linha decorativa
    draw.rounded_rectangle(
        [26 + badge + 42, 262, width - 40, 270],
        radius=4,
        fill=(148, 163, 184, 160),
    )
    return image


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    logo = build_logo()
    logo.save(OUTPUT, format="PNG")
    print(f"Logomarca provisória gerada em: {OUTPUT} ({logo.width}x{logo.height})")


if __name__ == "__main__":
    main()
