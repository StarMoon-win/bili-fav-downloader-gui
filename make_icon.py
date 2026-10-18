# -*- coding: utf-8 -*-
"""生成程序图标（build 时用一次，产物提交进仓库即可）

跑法：python make_icon.py
输出：assets/icon.ico（多尺寸）+ assets/icon.png（预览用）
"""
from pathlib import Path

from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent
OUT = BASE / "assets"
SIZE = 512


def rounded_gradient(size: int = SIZE) -> Image.Image:
    """蓝色渐变 + 圆角底"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size))
    px = grad.load()
    top, bottom = (96, 165, 250), (37, 99, 235)      # #60a5fa -> #2563eb
    for y in range(size):
        t = y / (size - 1)
        px_row = (
            int(top[0] + (bottom[0] - top[0]) * t),
            int(top[1] + (bottom[1] - top[1]) * t),
            int(top[2] + (bottom[2] - top[2]) * t),
            255,
        )
        for x in range(size):
            px[x, y] = px_row

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255)
    img.paste(grad, (0, 0), mask)
    return img


def draw_glyph(img: Image.Image) -> Image.Image:
    """白色下载箭头 + 底座"""
    d = ImageDraw.Draw(img)
    s = img.size[0]
    cx = s / 2
    w = s * 0.11                       # 竖杆宽度

    # 竖杆
    d.rounded_rectangle([cx - w / 2, s * 0.20, cx + w / 2, s * 0.56],
                        radius=w / 2, fill=(255, 255, 255, 255))
    # 箭头
    d.polygon([(cx - s * 0.20, s * 0.50),
               (cx + s * 0.20, s * 0.50),
               (cx, s * 0.70)], fill=(255, 255, 255, 255))
    # 底座托盘
    d.rounded_rectangle([s * 0.24, s * 0.76, s * 0.76, s * 0.84],
                        radius=s * 0.04, fill=(255, 255, 255, 235))
    return img


def main() -> None:
    OUT.mkdir(exist_ok=True)
    img = draw_glyph(rounded_gradient())
    img.save(OUT / "icon.png")

    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(OUT / "icon.ico", format="ICO", sizes=sizes)
    print("已生成", OUT / "icon.ico", (OUT / "icon.ico").stat().st_size, "字节")


if __name__ == "__main__":
    main()
