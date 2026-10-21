"""Ilustração "pessoa no cinema" (sem texto) para o ícone e a tela de abertura do canal.
Uso: python tools/cinema_art.py [pasta]   — sem pasta, grava direto em roku-channel/images."""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

INK = (10, 8, 20)
SCREEN_TOP, SCREEN_BOT = (255, 226, 170), (246, 150, 92)
VELVET, VELVET_D = (178, 34, 52), (110, 18, 34)
GOLD = (240, 198, 92)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def blur_layer(size, draw_fn, radius):
    m = Image.new("L", size, 0)
    draw_fn(ImageDraw.Draw(m))
    return m.filter(ImageFilter.GaussianBlur(radius))


def scene(w, h, ss=4, zoom=1.0):
    """zoom < 1 afasta a cena (para a tela de abertura, mais ar em volta)."""
    W, H = w * ss, h * ss
    u = min(W / 336, H / 210) * zoom          # unidade: 1 = 1 px do ícone 336×210
    cx = W / 2

    # sala escura, com leve tom roxo
    img = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=lerp((34, 20, 58), (8, 6, 14), y / H) + (255,))

    # tela (luz quente) e brilho que ela joga na sala
    sw, sh = 230 * u, 96 * u
    sx0, sy0 = cx - sw / 2, H / 2 - 92 * u
    glow = blur_layer((W, H), lambda g: g.rounded_rectangle([sx0, sy0, sx0 + sw, sy0 + sh], 6 * u, fill=200), 40 * u)
    img = Image.composite(Image.new("RGBA", (W, H), (250, 170, 110, 255)), img, glow)
    screen = Image.new("RGBA", (int(sw), int(sh)))
    sd = ImageDraw.Draw(screen)
    for y in range(int(sh)):
        sd.line([(0, y), (sw, y)], fill=lerp(SCREEN_TOP, SCREEN_BOT, y / sh) + (255,))
    # na tela: um pôr do sol de cinema (sol e silhueta de montanhas)
    sd.ellipse([sw * 0.58, sh * 0.28, sw * 0.58 + sh * 0.42, sh * 0.28 + sh * 0.42], fill=(255, 246, 214, 255))
    sd.polygon([(0, sh), (0, sh * 0.72), (sw * 0.2, sh * 0.5), (sw * 0.38, sh * 0.7), (sw * 0.55, sh * 0.55),
                (sw * 0.78, sh * 0.78), (sw, sh * 0.62), (sw, sh)], fill=(150, 70, 80, 255))
    mask = Image.new("L", screen.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, sw - 1, sh - 1], 5 * u, fill=255)
    screen.putalpha(mask)
    img.alpha_composite(screen, (int(sx0), int(sy0)))

    # facho do projetor, de trás da plateia até a tela
    beam = blur_layer((W, H), lambda g: g.polygon(
        [(cx + 40 * u, H + 10 * u), (sx0 + sw * 0.15, sy0 + sh * 0.2), (sx0 + sw * 0.85, sy0 + sh * 0.2)], fill=70), 10 * u)
    img = Image.composite(Image.new("RGBA", (W, H), (255, 236, 200, 255)), img, beam)
    d = ImageDraw.Draw(img)
    for px, py, r in [(0.47, 0.62, 1.6), (0.55, 0.5, 1.2), (0.6, 0.66, 1.0), (0.51, 0.42, 0.9)]:
        d.ellipse([W * px - r * u, H * py - r * u, W * px + r * u, H * py + r * u], fill=(255, 245, 220, 200))

    # poltronas vizinhas (encostos) à esquerda e à direita
    base = H / 2 + 74 * u
    for dx in (-118, -74, 74, 118):
        x = cx + dx * u
        d.rounded_rectangle([x - 20 * u, base - 44 * u, x + 20 * u, base + 30 * u], 12 * u, fill=VELVET_D)
        d.rounded_rectangle([x - 16 * u, base - 40 * u, x + 16 * u, base + 30 * u], 10 * u, fill=VELVET)

    # a pessoa, de costas: silhueta com contorno de luz da tela
    person = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    p = ImageDraw.Draw(person)
    hr = 17 * u
    hx, hy = cx, base - 70 * u
    p.ellipse([hx - hr, hy - hr * 1.08, hx + hr, hy + hr * 1.08], fill=INK)                       # cabeça
    p.rounded_rectangle([hx - 7 * u, hy + 10 * u, hx + 7 * u, hy + 26 * u], 3 * u, fill=INK)        # pescoço
    p.chord([hx - 36 * u, hy + 18 * u, hx + 36 * u, hy + 78 * u], 180, 360, fill=INK)                  # ombros
    p.rectangle([hx - 36 * u, hy + 47 * u, hx + 36 * u, base + 40 * u], fill=INK)                     # costas
    rim = person.getchannel("A").filter(ImageFilter.GaussianBlur(2.2 * u))
    edge = Image.new("RGBA", (W, H), (255, 200, 140, 255))
    edge.putalpha(rim.point(lambda a: 150 if 20 < a < 235 else 0))
    img.alpha_composite(edge, (0, int(-1.5 * u)))
    img.alpha_composite(person)
    d = ImageDraw.Draw(img)

    # encosto da poltrona dela, à frente das costas
    d.rounded_rectangle([cx - 48 * u, base - 8 * u, cx + 48 * u, base + 60 * u], 14 * u, fill=VELVET_D)
    d.rounded_rectangle([cx - 43 * u, base - 4 * u, cx + 43 * u, base + 60 * u], 12 * u, fill=VELVET)
    for i in (-1, 0, 1):                                                                          # costuras
        d.line([(cx + i * 22 * u, base + 4 * u), (cx + i * 22 * u, base + 60 * u)], fill=VELVET_D, width=int(1.6 * u))

    # balde de pipoca no braço da poltrona
    bx, by, bw, bh = cx + 58 * u, base - 2 * u, 26 * u, 30 * u
    for k in range(9):                                                                            # pipocas
        a = k / 8 * math.pi
        px_ = bx + math.cos(a) * bw * 0.42
        py_ = by - bh - 3 * u - math.sin(a) * 7 * u
        d.ellipse([px_ - 5 * u, py_ - 5 * u, px_ + 5 * u, py_ + 5 * u], fill=(255, 238, 190))
    d.polygon([(bx - bw / 2, by - bh), (bx + bw / 2, by - bh), (bx + bw * 0.36, by), (bx - bw * 0.36, by)], fill=(250, 246, 238))
    for t in (0.2, 0.6):
        d.polygon([(bx - bw / 2 + bw * t, by - bh), (bx - bw / 2 + bw * (t + 0.2), by - bh),
                   (bx - bw * 0.36 + bw * 0.72 * (t + 0.2), by), (bx - bw * 0.36 + bw * 0.72 * t, by)], fill=(222, 50, 60))

    # estrela dourada discreta no canto da tela (o "favorito")
    sr = 9 * u
    scx, scy = sx0 + sw - 16 * u, sy0 + 16 * u
    d.polygon([(scx + (sr if i % 2 == 0 else sr * 0.45) * math.cos(math.radians(-90 + i * 36)),
                scy + (sr if i % 2 == 0 else sr * 0.45) * math.sin(math.radians(-90 + i * 36))) for i in range(10)], fill=GOLD)

    return img.resize((w, h), Image.LANCZOS).convert("RGB")


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "roku-channel", "images")
    os.makedirs(out, exist_ok=True)
    scene(336, 210).save(os.path.join(out, "icon_hd.png"))
    scene(246, 140).save(os.path.join(out, "icon_sd.png"))
    scene(1920, 1080, ss=2, zoom=0.62).save(os.path.join(out, "splash_fhd.jpg"), quality=92)
    print("ok")
