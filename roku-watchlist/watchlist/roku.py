"""Controle do Roku pela rede (ECP): abrir títulos, escolher perfil, buscar pela tela."""
import socket
import threading
import time
import urllib.parse

import requests

from .common import CONFIG, CONFIG_PATH, log, save_json


# ---------- Roku ----------

def discover_roku():
    """Procura um Roku na rede (SSDP)."""
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
           'MAN: "ssdp:discover"\r\nMX: 2\r\nST: roku:ecp\r\n\r\n').encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3)
    try:
        s.sendto(msg, ("239.255.255.250", 1900))
        while True:
            data, addr = s.recvfrom(2048)
            if b"roku" in data.lower():
                return addr[0]
    except OSError:
        return None
    finally:
        s.close()


def roku_ip(refresh=False):
    ip = CONFIG.get("roku_ip")
    if refresh or not ip:
        found = discover_roku()
        if found and found != ip:
            CONFIG["roku_ip"] = found
            save_json(CONFIG_PATH, CONFIG)
            ip = found
    return ip


def roku_post(path):
    """POST para o ECP do Roku; tenta redescobrir o IP se ele mudou."""
    last = None
    for refresh in (False, True):
        ip = roku_ip(refresh)
        if not ip:
            continue
        try:
            r = requests.post(f"http://{ip}:8060/{path}", timeout=6)
            if r.status_code == 403:
                return False, ("O Roku recusou o comando. No Roku: Configurações › Sistema › "
                               "Configurações avançadas do sistema › Controle por apps móveis › "
                               "Acesso à rede › Permissivo.")
            if r.ok:
                return True, None
            last = f"Roku respondeu {r.status_code}"
        except requests.RequestException as e:
            last = f"Roku não respondeu ({e.__class__.__name__})"
    log.warning("comando ao Roku falhou (%s): %s", path, last)
    return False, last or "Roku não encontrado na rede"


KEYS = {"Home", "Back", "Select", "Up", "Down", "Left", "Right", "Play", "Rev", "Fwd",
        "InstantReplay", "Info", "VolumeUp", "VolumeDown", "VolumeMute", "PowerOff", "PowerOn"}


def roku_active_app():
    try:
        r = requests.get(f"http://{roku_ip()}:8060/query/active-app", timeout=4)
        return r.text
    except requests.RequestException:
        return ""


def play_with_profile(link, rule):
    """Para apps que abrem na escolha de perfil e perdem o link (Disney+):
    se o app já está aberto, manda o link direto; senão abre, escolhe o perfil
    e manda o link de novo."""
    app_id = link.split("?")[0].split("/")[1]
    if "?" in link and f'id="{app_id}"' in roku_active_app():
        return roku_post(link)
    ok, err = roku_post(link)
    if not ok:
        return ok, err

    def run():
        time.sleep(rule.get("wait", 12))
        for k in rule.get("keys", []):
            if k in KEYS:
                roku_post(f"keypress/{k}")
                time.sleep(0.7)
        if rule.get("relaunch_after") is not None and "?" in link:
            time.sleep(rule["relaunch_after"])
            roku_post(link)

    threading.Thread(target=run, daemon=True).start()
    return True, None


busy = threading.Lock()


def roku_ui_search(title, app_id):
    """Imita o controle: Pesquisar no menu do Roku, digita o título, abre o 1º
    resultado e aperta o 1º "Assistir agora"; depois escolhe o perfil do app.
    (O comando de busca do ECP não acha nada no catálogo brasileiro; a busca
    digitada na tela acha.)"""
    if not busy.acquire(blocking=False):
        return False, "Já estou abrindo outro título no Roku, aguarde."

    def key(k, wait=0.45):
        roku_post(f"keypress/{k}")
        time.sleep(wait)

    def run():
        try:
            key("Home", 4)
            for _ in range(5):          # Tela inicial → Pesquisar
                key("Down", 0.5)
            key("Select", 3.5)
            for ch in title.lower():
                key("Lit_" + urllib.parse.quote(ch, safe=""), 0.25)
            time.sleep(3)
            for _ in range(6):          # do "a" do teclado até o 1º resultado
                key("Right")
            time.sleep(1)
            key("Select", 4)            # página do título
            key("Select", 0.5)          # 1º "Assistir agora"
            rule = (CONFIG.get("after_launch") or {}).get(app_id)
            if rule:
                time.sleep(rule.get("wait", 14))
                for k in rule.get("keys", []):
                    key(k, 0.7)
        finally:
            busy.release()

    threading.Thread(target=run, daemon=True).start()
    return True, None


def roku_search(title, year, kind):
    q = {"keyword": title, "type": "series" if kind in ("tvSeries", "tvMiniSeries") else "movie",
         "launch": "true"}
    return roku_post("search/browse?" + urllib.parse.urlencode(q))


def play_link(link, title, title_pt=None, kind=None, year=None):
    if link.startswith("search:"):
        return roku_ui_search(title_pt or title, link.split(":", 1)[1])
    if link.startswith("launch/"):
        rule = (CONFIG.get("after_launch") or {}).get(link.split("?")[0].split("/")[1])
        return play_with_profile(link, rule) if rule else roku_post(link)
    return roku_search(title, year, kind)
