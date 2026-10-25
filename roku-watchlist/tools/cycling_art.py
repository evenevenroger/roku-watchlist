"""Ícones e tela de abertura do canal de ciclismo (desenhados aqui, sem imagens de terceiros)."""
import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "roku-ciclismo", "images")
BG, GOLD, WHITE, RED = (14, 15, 19), (227, 193, 111), (236, 238, 243), (255, 90, 90)


def font(size, bold=True):
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def bike(d, cx, cy, s, color, width):
    """Bicicleta de estrada vista de lado, centrada em (cx, cy), escala s."""
    r = 0.42 * s
    rear, front = (cx - 0.62 * s, cy + 0.25 * s), (cx + 0.62 * s, cy + 0.25 * s)
    for x, y in (rear, front):
        d.ellipse([x - r, y - r, x + r, y + r], outline=color, width=width)
    crank = (cx - 0.08 * s, cy + 0.25 * s)
    seat = (cx - 0.25 * s, cy - 0.42 * s)
    head = (cx + 0.42 * s, cy - 0.38 * s)
    for a, b in ((rear, crank), (crank, seat), (seat, rear), (seat, head), (head, crank), (head, front)):
        d.line([a, b], fill=color, width=width)
    d.line([(seat[0] - 0.12 * s, seat[1] - 0.06 * s), (seat[0] + 0.1 * s, seat[1] - 0.06 * s)], fill=color, width=width)
    d.line([head, (head[0] + 0.14 * s, head[1] - 0.1 * s)], fill=color, width=width)
    d.arc([head[0] + 0.06 * s, head[1] - 0.12 * s, head[0] + 0.3 * s, head[1] + 0.12 * s], 270, 90, fill=color, width=width)
    d.ellipse([crank[0] - 0.07 * s, crank[1] - 0.07 * s, crank[0] + 0.07 * s, crank[1] + 0.07 * s], outline=color, width=width)


def card(w, h, title_size, sub_size, bike_scale, with_text=True):
    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, w, max(4, h // 40)], fill=GOLD)
    if with_text:
        bike(d, w * 0.5, h * 0.36, bike_scale, GOLD, max(3, int(bike_scale / 22)))
        for text, size, color, y in (("Ciclismo", title_size, WHITE, h * 0.66), ("WorldTour", sub_size, GOLD, h * 0.66 + title_size * 1.1)):
            f = font(size)
            tw = d.textlength(text, font=f)
            d.text(((w - tw) / 2, y), text, font=f, fill=color)
    else:
        bike(d, w * 0.5, h * 0.45, bike_scale, GOLD, max(3, int(bike_scale / 22)))
    return im


os.makedirs(OUT, exist_ok=True)
card(540, 405, 64, 40, 200).save(os.path.join(OUT, "icon_fhd.png"))
card(290, 218, 36, 22, 108).save(os.path.join(OUT, "icon_hd.png"))
card(246, 140, 26, 16, 70).save(os.path.join(OUT, "icon_sd.png"))
card(1920, 1080, 120, 72, 620).save(os.path.join(OUT, "splash_fhd.jpg"), quality=90)
print("ok", OUT)
