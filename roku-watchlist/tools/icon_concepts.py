"""Quatro conceitos de ícone para o canal (sem texto). Gera uma folha de comparação.
Uso: python tools/icon_concepts.py [pasta de saída]"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

S = 4                      # desenha 4× maior e reduz: bordas suaves
W, H = 336 * S, 210 * S
GOLD, GOLD_D = (240, 198, 92), (176, 128, 40)
CREAM = (250, 240, 220)
INK = (18, 14, 32)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def gradient(w, h, top, bottom, radial=None):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=lerp(top, bottom, y / h))
    if radial:
        cx, cy, r, col, alpha = radial
        glow = Image.new("L", (w, h), 0)
        ImageDraw.Draw(glow).ellipse([cx - r, cy - r, cx + r, cy + r], fill=alpha)
        glow = glow.filter(ImageFilter.GaussianBlur(r * 0.5))
        img = Image.composite(Image.new("RGB", (w, h), col), img, glow)
    return img.convert("RGBA")


def star_pts(cx, cy, r, inner=0.45, rot=-90):
    pts = []
    for i in range(10):
        a = math.radians(rot + i * 36)
        rr = r if i % 2 == 0 else r * inner
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def shadow(layer, blur, offset, opacity=0.5):
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    sh.putalpha(layer.getchannel("A").point(lambda a: int(a * opacity)))
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    out = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    out.alpha_composite(sh, offset)
    return out


def finish(img):
    return img.resize((W // S, H // S), Image.LANCZOS).convert("RGB")


# 1 · Fita-marcador: tira de filme dourada com corte em V de marcador, estrela num quadro
def bookmark():
    img = gradient(W, H, (36, 22, 78), (12, 10, 26), (W * 0.5, H * 0.3, W * 0.45, (90, 50, 170), 160))
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    bw, x0, y0, y1 = int(W * 0.24), int(W * 0.38), -10, int(H * 0.92)
    notch = int(bw * 0.42)
    d.polygon([(x0, y0), (x0 + bw, y0), (x0 + bw, y1), (x0 + bw / 2, y1 - notch), (x0, y1)], fill=GOLD)
    d.polygon([(x0 + bw * 0.5, y0), (x0 + bw, y0), (x0 + bw, y1), (x0 + bw / 2, y1 - notch)],
              fill=(222, 176, 72))                                                  # meio-tom do relevo
    hole_w, hole_h = bw * 0.11, bw * 0.08
    for y in range(int(18 * S), int(y1 - notch - 10 * S), int(hole_h * 2.1)):     # furos da película
        for hx in (x0 + bw * 0.07, x0 + bw * 0.82):
            d.rounded_rectangle([hx, y, hx + hole_w, y + hole_h], 2 * S, fill=INK)
    fx0, fx1 = x0 + bw * 0.24, x0 + bw * 0.76
    for i, fy in enumerate([H * 0.08, H * 0.36]):                                  # quadros do filme
        d.rounded_rectangle([fx0, fy, fx1, fy + H * 0.24], 3 * S, fill=(30, 18, 60))
    d.polygon(star_pts((fx0 + fx1) / 2, H * 0.48, bw * 0.2), fill=GOLD)
    img.alpha_composite(shadow(lay, 10 * S, (5 * S, 9 * S)))
    img.alpha_composite(lay)
    return finish(img)


# 2 · Ingresso: ticket inclinado com picote, meia-luas e estrela
def ticket():
    img = gradient(W, H, (20, 16, 44), (8, 8, 18), (W * 0.5, H * 0.55, W * 0.5, (120, 40, 70), 120))
    tw, th = int(W * 0.62), int(H * 0.56)
    t = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(t)
    d.rounded_rectangle([0, 0, tw - 1, th - 1], 10 * S, fill=(236, 90, 78))
    stub = int(tw * 0.7)
    d.rectangle([stub, 0, tw, th], fill=(214, 70, 64))
    r = th * 0.13
    for cx in (stub,):                                                             # meia-luas do picote
        d.ellipse([cx - r, -r, cx + r, r], fill=(0, 0, 0, 0))
        d.ellipse([cx - r, th - r, cx + r, th + r], fill=(0, 0, 0, 0))
    for y in range(int(r * 1.3), int(th - r * 1.3), int(6 * S)):                   # picote
        d.ellipse([stub - 1.4 * S, y, stub + 1.4 * S, y + 2.8 * S], fill=(0, 0, 0, 0))
    m = int(th * 0.12)
    d.rounded_rectangle([m, m, stub - m, th - m], 6 * S, outline=CREAM + (200,), width=2 * S)
    d.polygon(star_pts((m + stub - m) / 2, th / 2, th * 0.27), fill=GOLD)
    for i in range(3):                                                             # 3 estrelinhas no canhoto
        d.polygon(star_pts(stub + (tw - stub) / 2, th * (0.3 + i * 0.2), th * 0.06), fill=CREAM)
    t = t.rotate(-10, resample=Image.BICUBIC, expand=True)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    lay.alpha_composite(t, ((W - t.width) // 2, (H - t.height) // 2))
    img.alpha_composite(shadow(lay, 12 * S, (6 * S, 12 * S), 0.6))
    img.alpha_composite(lay)
    return finish(img)


# 3 · Projetor: facho de luz quente do canto sobre uma tela com play
def projector():
    img = gradient(W, H, (14, 12, 30), (6, 6, 12))
    sx0, sy0, sx1, sy1 = W * 0.38, H * 0.18, W * 0.88, H * 0.74                   # tela
    beam = Image.new("L", (W, H), 0)
    ImageDraw.Draw(beam).polygon([(W * 0.06, H * 0.86), (sx0, sy0), (sx1, sy0), (sx1, sy1), (sx0, sy1)], fill=120)
    beam = beam.filter(ImageFilter.GaussianBlur(14 * S))
    img = Image.composite(Image.new("RGBA", (W, H), (255, 214, 140, 255)), img, beam)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([sx0, sy0, sx1, sy1], 5 * S, fill=(255, 238, 205), outline=(255, 250, 235), width=2 * S)
    cx, cy, r = (sx0 + sx1) / 2, (sy0 + sy1) / 2, (sy1 - sy0) * 0.26
    d.polygon([(cx - r * 0.7, cy - r), (cx - r * 0.7, cy + r), (cx + r * 0.95, cy)], fill=(108, 63, 245))
    for i, (px, py, pr) in enumerate([(0.2, 0.34, 0.035), (0.28, 0.2, 0.022), (0.12, 0.55, 0.025)]):
        d.polygon(star_pts(W * px, H * py, H * pr * 3), fill=GOLD)                 # poeira estrelada no facho
    lens = (W * 0.06, H * 0.86)
    d.ellipse([lens[0] - 16 * S, lens[1] - 16 * S, lens[0] + 16 * S, lens[1] + 16 * S], fill=(255, 245, 220))
    return finish(img)


# 4 · Pipoca de estrelas: balde listrado com estrelas saltando
def popcorn():
    img = gradient(W, H, (42, 18, 70), (14, 8, 24), (W * 0.5, H * 0.2, W * 0.5, (150, 60, 140), 130))
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    bx, by, bw, bh = W * 0.5, H * 0.95, W * 0.3, H * 0.5
    top_w, bot_w = bw, bw * 0.72
    poly = [(bx - top_w / 2, by - bh), (bx + top_w / 2, by - bh), (bx + bot_w / 2, by), (bx - bot_w / 2, by)]
    stars = [(0.5, 0.2, 0.15, 0), (0.36, 0.34, 0.1, 15), (0.64, 0.32, 0.11, -12), (0.42, 0.1, 0.07, 20),
             (0.6, 0.1, 0.06, -20), (0.27, 0.16, 0.05, 30), (0.73, 0.18, 0.055, 10)]
    for px, py, pr, rot in stars:
        d.polygon(star_pts(W * px, H * py, H * pr * 1.6, 0.48, -90 + rot), fill=GOLD if pr > 0.06 else CREAM)
    d.polygon(poly, fill=CREAM)
    n = 5
    for i in range(n):                                                             # listras vermelhas
        if i % 2 == 0:
            t0, t1 = i / n, (i + 1) / n
            d.polygon([(bx - top_w / 2 + top_w * t0, by - bh), (bx - top_w / 2 + top_w * t1, by - bh),
                       (bx - bot_w / 2 + bot_w * t1, by), (bx - bot_w / 2 + bot_w * t0, by)], fill=(226, 54, 64))
    d.rounded_rectangle([bx - top_w / 2 - 4 * S, by - bh - 6 * S, bx + top_w / 2 + 4 * S, by - bh + 6 * S], 4 * S, fill=(250, 250, 250))
    img.alpha_composite(shadow(lay, 10 * S, (4 * S, 8 * S)))
    img.alpha_composite(lay)
    return finish(img)


CONCEPTS = {"1-fita-marcador": bookmark, "2-ingresso": ticket, "3-projetor": projector, "4-pipoca-estrelas": popcorn}

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    imgs = []
    for name, fn in CONCEPTS.items():
        im = fn()
        im.save(os.path.join(out, name + ".png"))
        imgs.append(im)
    sheet = Image.new("RGB", (336 * 2 + 30, 210 * 2 + 30), (30, 30, 36))
    for i, im in enumerate(imgs):
        sheet.paste(im, (10 + (i % 2) * 346, 10 + (i // 2) * 220))
    sheet.save(os.path.join(out, "folha.png"))
    print("ok")
