"""Ícone e tela de abertura do canal a partir da ilustração tools/cinema_source.png (quadrada).
Recorta faixas horizontais centradas na tela do cinema e na cabeça da pessoa. Uso: python tools/channel_art.py"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "roku-channel", "images")


def band(img, ratio, center_y):
    """Recorte com a largura toda e a altura da proporção pedida, centrado em center_y (0..1)."""
    w, h = img.size
    ch = round(w / ratio)
    top = min(max(0, round(center_y * h - ch / 2)), h - ch)
    return img.crop((0, top, w, top + ch))


if __name__ == "__main__":
    src = Image.open(os.path.join(HERE, "tools", "cinema_source.png")).convert("RGB")
    icon = band(src, 336 / 210, 0.45)
    icon.resize((336, 210), Image.LANCZOS).save(os.path.join(OUT, "icon_hd.png"))
    icon.resize((246, 140), Image.LANCZOS).save(os.path.join(OUT, "icon_sd.png"))
    band(src, 16 / 9, 0.45).resize((1920, 1080), Image.LANCZOS).save(os.path.join(OUT, "splash_fhd.jpg"), quality=92)
    print("ok")
