"""Ícones da faixa de prêmio no pôster: leão (Veneza) e urso (Berlim), em versão escura e dourada.
Silhuetas de cabeça de frente, com olhos e focinho vazados, para continuar legíveis em 40×40.
Uso: python tools/award_icons.py [pasta]   — sem pasta, grava em roku-channel/images."""
import math
import os
import sys

from PIL import Image, ImageDraw

SIZE, SS = 40, 16                       # desenha 16× maior (unidade 0..100) e reduz
DARK, GOLD = (42, 32, 8), (227, 193, 111)


def canvas():
    m = Image.new("L", (100 * SS, 100 * SS), 0)
    return m, ImageDraw.Draw(m)


def circ(d, x, y, r, v=255):
    d.ellipse([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], fill=v)


def ell(d, x, y, rx, ry, v=255):
    d.ellipse([(x - rx) * SS, (y - ry) * SS, (x + rx) * SS, (y + ry) * SS], fill=v)


def poly(d, pts, v=255):
    d.polygon([(x * SS, y * SS) for x, y in pts], fill=v)


LION_FACE = [(50, 22), (62, 22), (72, 30), (86, 40), (93, 50), (91, 57), (84, 60), (79, 63),
             (82, 70), (74, 77), (60, 80), (52, 70)]


def lion():
    """Cabeça de perfil, virada para a direita: juba em mechas pontudas e rosto separado por um vão."""
    m, d = canvas()
    pts = []
    for i in range(22):                              # juba: estrela irregular atrás do rosto
        a = math.radians(i * 360 / 22 - 90)
        r = 44 if i % 2 == 0 else 31
        pts.append((44 + r * math.cos(a) * 0.95, 52 + r * math.sin(a)))
    poly(d, pts)
    d.line([(x * SS, y * SS) for x, y in LION_FACE + LION_FACE[:1]], fill=0, width=7 * SS, joint="curve")
    poly(d, LION_FACE)                               # rosto e focinho
    poly(d, [(54, 24), (58, 10), (66, 24)])          # orelha
    ell(d, 72, 40, 3.5, 3, 0)                        # olho
    d.line([(79 * SS, 63 * SS), (70 * SS, 64 * SS)], fill=0, width=3 * SS)   # boca
    return m


def bear():
    m, d = canvas()
    circ(d, 25, 28, 15)                              # orelhas
    circ(d, 75, 28, 15)
    circ(d, 25, 28, 6.5, 0)
    circ(d, 75, 28, 6.5, 0)
    ell(d, 50, 57, 38, 35)                           # cabeça
    ell(d, 37, 50, 4.5, 5, 0)                        # olhos
    ell(d, 63, 50, 4.5, 5, 0)
    ell(d, 50, 72, 16, 12, 0)                        # focinho vazado
    ell(d, 50, 67, 7, 5)                             # nariz
    return m


def colored(mask, rgb):
    a = mask.resize((SIZE, SIZE), Image.LANCZOS)
    im = Image.new("RGBA", (SIZE, SIZE), rgb + (0,))
    im.putalpha(a)
    return im


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "roku-channel", "images")
    os.makedirs(out, exist_ok=True)
    for name, fn in (("lion", lion), ("bear", bear)):
        mask = fn()
        colored(mask, DARK).save(os.path.join(out, name + "_dark.png"))
        colored(mask, GOLD).save(os.path.join(out, name + "_gold.png"))
    print("ok")
