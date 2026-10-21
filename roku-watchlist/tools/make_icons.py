"""Gera o ícone e a tela de abertura do canal (sem texto): três pôsteres em leque,
o da frente com play, e um selo de estrela. Uso: python tools/make_icons.py"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "roku-channel", "images")
BG_IN, BG_OUT = (46, 26, 110), (14, 15, 19)
POSTERS = [((233, 99, 81), (122, 32, 54)),     # coral → vinho
           ((47, 170, 160), (16, 70, 92)),     # verde-água → petróleo
           ((108, 63, 245), (52, 22, 140))]    # roxo do canal
GOLD = (227, 193, 111)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def background(w, h):
    """Fundo com brilho roxo no centro, escurecendo para as bordas."""
    img = Image.new("RGB", (w, h))
    px = img.load()
    cx, cy, r = w / 2, h * 0.55, math.hypot(w, h) / 1.6
    for y in range(h):
        for x in range(w):
            t = min(1.0, math.hypot(x - cx, y - cy) / r)
            px[x, y] = lerp(BG_IN, BG_OUT, t ** 0.8)
    return img


def poster(pw, ph, top, bottom, radius):
    """Pôster com degradê vertical, cantos arredondados e um brilho diagonal."""
    p = Image.new("RGBA", (pw, ph))
    d = ImageDraw.Draw(p)
    for y in range(ph):
        d.line([(0, y), (pw, y)], fill=lerp(top, bottom, y / ph) + (255,))
    shine = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    ImageDraw.Draw(shine).polygon([(0, 0), (pw * 0.55, 0), (0, ph * 0.45)], fill=(255, 255, 255, 34))
    p = Image.alpha_composite(p, shine)
    mask = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, pw - 1, ph - 1], radius, fill=255)
    p.putalpha(mask)
    return p


def star(d, cx, cy, r, fill):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill)


def scene(w, h, scale, size=0.66):
    """Desenha em tamanho grande (scale×) e reduz no fim, para bordas suaves."""
    W, H = w * scale, h * scale
    img = background(w, h).resize((W, H), Image.BICUBIC).convert("RGBA")
    ph = int(H * size)
    pw = int(ph * 0.68)
    radius = int(pw * 0.09)
    cx, cy = W // 2, int(H * 0.54)
    for i, (angle, dx) in enumerate([(-14, -0.62), (14, 0.62), (0, 0)]):
        top, bottom = POSTERS[i]
        p = poster(pw, ph, top, bottom, radius)
        if angle:
            p = p.rotate(angle, resample=Image.BICUBIC, expand=True)
        # sombra suave
        sh = Image.new("RGBA", p.size, (0, 0, 0, 0))
        sh.putalpha(p.getchannel("A").point(lambda a: int(a * 0.55)))
        sh = sh.filter(ImageFilter.GaussianBlur(scale * 6))
        x = int(cx + dx * pw - p.width / 2)
        y = int(cy - p.height / 2 + (scale * 6 if angle else 0))
        img.alpha_composite(sh, (x + scale * 4, y + scale * 8))
        img.alpha_composite(p, (x, y))
    d = ImageDraw.Draw(img)
    # play no pôster da frente
    r = pw * 0.2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 235))
    tri = r * 0.55
    d.polygon([(cx - tri * 0.55, cy - tri), (cx - tri * 0.55, cy + tri), (cx + tri, cy)], fill=(52, 22, 140, 255))
    # selo de estrela no canto do pôster da frente
    sx, sy, sr = cx + pw * 0.42, cy - ph * 0.42, pw * 0.2
    d.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=GOLD + (255,), outline=(14, 15, 19, 255), width=scale * 3)
    star(d, sx, sy, sr * 0.62, (42, 32, 8, 255))
    return img.resize((w, h), Image.LANCZOS).convert("RGB")


if __name__ == "__main__":
    scene(336, 210, 4).save(os.path.join(OUT, "icon_hd.png"))
    scene(246, 140, 4).save(os.path.join(OUT, "icon_sd.png"))
    scene(1920, 1080, 1, size=0.42).save(os.path.join(OUT, "splash_fhd.jpg"), quality=92)
    print("ok")
