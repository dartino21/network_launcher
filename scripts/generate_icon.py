"""Генерирует PNG/ICO-иконку Network Launcher с помощью Pillow."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def draw_icon(size: int = 512) -> Image.Image:
    scale = size / 512
    image = Image.new("RGBA", (size, size), (13, 16, 23, 255))
    draw = ImageDraw.Draw(image)

    def xy(values):
        return tuple(int(value * scale) for value in values)

    draw.rounded_rectangle(xy((40, 40, 472, 472)), radius=int(108 * scale), fill=(21, 26, 36, 255))
    draw.ellipse(xy((86, 86, 246, 246)), fill=(91, 140, 255, 40))
    draw.ellipse(xy((260, 260, 426, 426)), fill=(55, 200, 138, 35))

    links = [((154, 170), (344, 150)), ((154, 170), (248, 344)), ((344, 150), (360, 342)), ((248, 344), (360, 342))]
    for start, end in links:
        draw.line(xy((*start, *end)), fill=(126, 164, 255, 255), width=max(4, int(16 * scale)))

    nodes = [((154, 170), 54, (91, 140, 255, 255)), ((344, 150), 44, (118, 160, 255, 255)), ((248, 344), 45, (91, 140, 255, 255)), ((360, 342), 55, (55, 200, 138, 255))]
    for (cx, cy), radius, color in nodes:
        draw.ellipse(xy((cx - radius, cy - radius, cx + radius, cy + radius)), fill=(13, 16, 23, 255), outline=color, width=max(4, int(17 * scale)))
        inner = int(radius * 0.35)
        draw.ellipse(xy((cx - inner, cy - inner, cx + inner, cy + inner)), fill=color)
    return image


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    image = draw_icon()
    image.save(ASSETS / "network_launcher.png")
    image.save(
        ASSETS / "network_launcher.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    main()
