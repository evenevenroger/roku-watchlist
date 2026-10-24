"""Controle do Roku pela rede (ECP): abrir títulos, escolher perfil, buscar pela tela."""
import socket
import threading
import time
import urllib.parse
import ipaddress
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import requests

from .common import CONFIG, CONFIG_PATH, lan_ip, log, save_json

_discovery_lock = threading.Lock()
_health = {"at": 0, "value": None}


def probe_roku(ip, timeout=1.5):
    """Só aceita um Roku real; o serial evita trocar de TV após mudança de IP."""
    try:
        address = ipaddress.ip_address(ip)
        if address.version != 4 or not address.is_private or address.is_loopback:
            return None
        with requests.Session() as session:
            session.trust_env = False
            response = session.get(f"http://{address}:8060/query/device-info", timeout=timeout)
        response.raise_for_status()
        node = ET.fromstring(response.content)
        serial = node.findtext("serial-number")
        if node.tag != "device-info" or not serial:
            return None
        if CONFIG.get("roku_serial") and serial != CONFIG["roku_serial"]:
            return None
        return {"connected": True, "ip": str(address), "serial": serial,
                "name": node.findtext("user-device-name") or node.findtext("model-name") or "Roku",
                "error": None}
    except (requests.RequestException, ValueError, ET.ParseError):
        return None


# ---------- Roku ----------

def discover_roku():
    """Procura um Roku na rede (SSDP)."""
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
           'MAN: "ssdp:discover"\r\nMX: 2\r\nST: roku:ecp\r\n\r\n').encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.5)
    try:
        s.bind((lan_ip(), 0))
        s.sendto(msg, ("239.255.255.250", 1900))
        deadline = time.monotonic() + 2.5
        while time.monotonic() < deadline:
            try:
                data, addr = s.recvfrom(2048)
                if b"roku" in data.lower() and probe_roku(addr[0]):
                    return addr[0]
            except socket.timeout:
                continue
    except OSError:
        pass  # Ainda tenta a rede local quando o roteador bloqueia multicast.
    finally:
        s.close()

    # Alguns roteadores bloqueiam multicast. Reserva limitada à rede IPv4 /24 do PC.
    # Sem identidade conhecida não escolhe arbitrariamente outra TV.
    if CONFIG.get("roku_serial"):
        local = ipaddress.ip_address(lan_ip())
        if local.is_private and not local.is_loopback:
            candidates = [str(ip) for ip in ipaddress.ip_network(f"{local}/24", strict=False).hosts()
                          if ip != local]
            with ThreadPoolExecutor(max_workers=32) as executor:
                hits = executor.map(lambda ip: probe_roku(ip, timeout=0.35), candidates)
                for hit in hits:
                    if hit:
                        return hit["ip"]
    return None


def roku_ip(refresh=False):
    ip = CONFIG.get("roku_ip")
    if refresh or not ip:
        with _discovery_lock:
            found = discover_roku()
            if found and found != ip:
                CONFIG["roku_ip"] = found
                save_json(CONFIG_PATH, CONFIG, indent=2)
                ip = found
    return ip


def roku_health(refresh=False):
    with _discovery_lock:
        if not refresh and time.monotonic() - _health["at"] < 15 and _health["value"]:
            return dict(_health["value"])
        ip = CONFIG.get("roku_ip")
        value = probe_roku(ip)
        if not value and refresh:
            ip = discover_roku()
            value = probe_roku(ip) if ip else None
        if value:
            if CONFIG.get("roku_ip") != value["ip"] or CONFIG.get("roku_serial") != value["serial"]:
                CONFIG.update(roku_ip=value["ip"], roku_serial=value["serial"])
                save_json(CONFIG_PATH, CONFIG, indent=2)
        else:
            value = {"connected": False, "ip": ip, "name": "Roku",
                     "error": "Roku não respondeu. Confira a energia, o Wi-Fi e o acesso por apps móveis."}
        _health.update(at=time.monotonic(), value=value)
        return dict(value)


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
