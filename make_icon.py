# -*- coding: utf-8 -*-
"""
生成 Windows 资源管理器能正常显示的 ICO。
要点：小尺寸必须用 BMP(DIB) 帧，不能用 PNG 帧，
      否则快捷方式会显示空白图标。
"""
import struct
import sys

from PIL import Image, ImageDraw

SRC = "assets/keyvisual.jpg"
BOX = (55, 55, 245, 245)      # 黄毛角色，右侧黑发角色已排除
SIZES = [16, 24, 32, 48, 64, 128, 256]


def rounded(img: Image.Image, radius_ratio=0.11) -> Image.Image:
    w, h = img.size
    r = int(min(w, h) * radius_ratio)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=255)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def bmp_frame(img: Image.Image) -> bytes:
    """把一张 RGBA 图转成 ICO 里的 BMP 帧数据（含 AND 掩码）"""
    w, h = img.size
    px = img.load()
    # XOR 部分：BGRA，自下而上
    xor = bytearray()
    for y in range(h - 1, -1, -1):
        for x in range(w):
            r, g, b, a = px[x, y]
            xor += bytes((b, g, r, a))
    # AND 掩码：1bpp，每行补齐到 4 字节；有 alpha 时全 0 即可
    row_bytes = ((w + 31) // 32) * 4
    mask = bytes(row_bytes * h)

    header = struct.pack(
        "<IiiHHIIiiII",
        40,            # biSize
        w,             # biWidth
        h * 2,         # biHeight（XOR + AND 叠加）
        1,             # biPlanes
        32,            # biBitCount
        0,             # biCompression
        len(xor) + len(mask),
        0, 0, 0, 0,
    )
    return header + bytes(xor) + mask


def build_ico(images: list, path: str):
    frames = [(im.size[0], im.size[1], bmp_frame(im)) for im in images]
    n = len(frames)
    out = bytearray(struct.pack("<HHH", 0, 1, n))
    offset = 6 + 16 * n
    for w, h, data in frames:
        out += struct.pack("<BBBBHHII",
                           w if w < 256 else 0,
                           h if h < 256 else 0,
                           0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for _w, _h, data in frames:
        out += data
    with open(path, "wb") as f:
        f.write(out)
    return len(out)


def main():
    src = Image.open(SRC).convert("RGB").crop(BOX)
    ims = []
    for s in SIZES:
        im = src.resize((s, s), Image.LANCZOS).convert("RGBA")
        ims.append(rounded(im) if s >= 32 else im)   # 小尺寸不加圆角，避免糊
    size = build_ico(ims, "assets/app.ico")
    # 同时存一张 png 供程序内部使用
    ims[-1].save("assets/app.png")
    print(f"app.ico 生成完成：{size/1024:.0f} KB，含 {len(SIZES)} 帧（BMP 格式）")
    for s in SIZES:
        print(f"  {s}x{s}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
