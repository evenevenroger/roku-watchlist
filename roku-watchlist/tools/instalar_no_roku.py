"""Instala os canais no Roku e gera o pacote do canal beta de ciclismo.

Uso (pelos atalhos .bat na pasta roku-watchlist):
    python tools/instalar_no_roku.py watchlist   instala o Minha Watchlist mais recente
    python tools/instalar_no_roku.py ciclismo    instala o Ciclismo WorldTour (tira o Watchlist do lugar)
    python tools/instalar_no_roku.py beta        instala o ciclismo, gera o .pkg assinado e põe o Watchlist de volta

A senha da página do Roku (usuário rokudev) fica em roku_senha.txt, ao lado deste projeto,
criado por você; se o arquivo não existir, o script pergunta e oferece guardar.
A senha da chave de assinatura (gerada pelo próprio Roku na primeira vez) fica em roku_chave.txt.
Os dois arquivos ficam fora do git.
"""
import getpass
import json
import os
import re
import socket
import sys
import time

import requests
from requests.auth import HTTPDigestAuth

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SENHA = os.path.join(BASE, "roku_senha.txt")
CHAVE = os.path.join(BASE, "roku_chave.txt")
PACOTES = os.path.join(BASE, "pacotes")
SERVER = "http://localhost:8790"
CHANNELS = {"watchlist": ("/roku-channel.zip", "MinhaWatchlist.zip"),
            "ciclismo": ("/ciclismo-channel.zip", "CiclismoWorldTour.zip")}


def roku_ip():
    with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
        ip = json.load(f).get("roku_ip")
    if not ip:
        sys.exit("config.json não tem roku_ip.")
    return ip


def password():
    if os.path.isfile(SENHA):
        with open(SENHA, encoding="utf-8") as f:
            value = f.read().strip()
        if value:
            return value
    value = getpass.getpass("Senha da página do Roku (usuário rokudev): ").strip()
    if value and input("Guardar em roku_senha.txt para as próximas vezes? [s/N] ").strip().lower() == "s":
        with open(SENHA, "w", encoding="utf-8") as f:
            f.write(value)
    return value


def build_zip(name):
    path, filename = CHANNELS[name]
    r = requests.get(SERVER + path, timeout=60)
    if r.status_code != 200:
        sys.exit(f"O servidor não gerou o canal ({r.status_code}): {r.text[:200]}")
    out = os.path.join(BASE, filename)
    with open(out, "wb") as f:
        f.write(r.content)
    return out


def install(name, ip, pw):
    zip_path = build_zip(name)
    print(f"Enviando {os.path.basename(zip_path)} para o Roku {ip}...")
    with open(zip_path, "rb") as f:
        r = requests.post(f"http://{ip}/plugin_install", auth=HTTPDigestAuth("rokudev", pw),
                          files={"archive": (os.path.basename(zip_path), f, "application/zip")},
                          data={"mysubmit": "Replace"}, timeout=120)
    if r.status_code == 401:
        sys.exit("O Roku recusou a senha. Confira roku_senha.txt.")
    text = re.sub(r"<[^>]+>", " ", r.text)
    if "Install Success" in text or "Identical to previous version" in text or "Received" in text:
        print("Instalado.")
        return
    sys.exit("O Roku não confirmou a instalação: " + " ".join(text.split())[:300])


def signing_key(ip):
    """Senha da chave de assinatura; na primeira vez, o Roku gera uma (genkey, porta 8080)."""
    if os.path.isfile(CHAVE):
        with open(CHAVE, encoding="utf-8") as f:
            for line in f:
                if line.lower().startswith("password:"):
                    return line.split(":", 1)[1].strip()
    print("Gerando a chave de assinatura no Roku (só na primeira vez)...")
    s = socket.create_connection((ip, 8080), timeout=10)
    s.sendall(b"genkey\n")
    out, end = b"", time.time() + 90
    while time.time() < end and b"DevID" not in out:
        try:
            out += s.recv(4096)
        except socket.timeout:
            pass
    s.close()
    text = out.decode("utf-8", "replace")
    pw = re.search(r"Password:\s*(\S+)", text)
    dev = re.search(r"DevID:\s*(\S+)", text)
    if not pw:
        sys.exit("O Roku não gerou a chave: " + text[-300:])
    with open(CHAVE, "w", encoding="utf-8") as f:
        f.write(f"Password: {pw.group(1)}\nDevID: {dev.group(1) if dev else ''}\n")
    print("Chave guardada em roku_chave.txt. Guarde também uma cópia: sem ela não dá para atualizar o canal beta.")
    return pw.group(1)


def package(ip, pw):
    with open(os.path.join(BASE, "roku-ciclismo", "manifest"), encoding="utf-8") as f:
        man = dict(line.strip().split("=", 1) for line in f if "=" in line)
    version = f'{man["major_version"]}.{man["minor_version"]}.{man["build_version"]}'
    print(f"Gerando o pacote assinado {version}...")
    r = requests.post(f"http://{ip}/plugin_package", auth=HTTPDigestAuth("rokudev", pw),
                      files={"mysubmit": (None, "Package"), "app_name": (None, f"Ciclismo WorldTour/{version}"),
                             "passwd": (None, signing_key(ip)), "pkg_time": (None, str(int(time.time() * 1000)))},
                      timeout=180)
    m = re.search(r'href="(pkgs/[^"]+\.pkg)"', r.text) or re.search(r'"(pkgs/[^"]+\.pkg)"', r.text)
    if not m:
        sys.exit("O Roku não gerou o pacote: " + " ".join(re.sub(r"<[^>]+>", " ", r.text).split())[:300])
    pkg = requests.get(f"http://{ip}/{m.group(1)}", auth=HTTPDigestAuth("rokudev", pw), timeout=120)
    os.makedirs(PACOTES, exist_ok=True)
    out = os.path.join(PACOTES, f"CiclismoWorldTour-{version}.pkg")
    with open(out, "wb") as f:
        f.write(pkg.content)
    print("Pacote pronto:", out)
    return out


def main():
    what = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    if what not in ("watchlist", "ciclismo", "beta"):
        sys.exit(__doc__)
    ip, pw = roku_ip(), password()
    if what == "beta":
        install("ciclismo", ip, pw)
        time.sleep(5)
        out = package(ip, pw)
        install("watchlist", ip, pw)
        print("\nMinha Watchlist de volta no Roku. Envie este pacote ao canal beta em developer.roku.com:\n  " + out)
    else:
        install(what, ip, pw)


if __name__ == "__main__":
    try:
        main()
    finally:
        if os.environ.get("PAUSE_AT_END"):
            input("\nAperte Enter para fechar.")
