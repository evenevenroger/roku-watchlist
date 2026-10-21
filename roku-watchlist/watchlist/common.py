"""Caminhos, configuração, leitura/gravação de JSON, estado da sincronização e registro de erros."""
import json
import logging
import os
import socket
import threading
from logging.handlers import RotatingFileHandler

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE, "config.json")
DATA_DIR = os.path.join(BASE, "data")
CACHE_PATH = os.path.join(DATA_DIR, "cache.json")
RECENT_PATH = os.path.join(DATA_DIR, "recent.json")   # títulos abertos pelo canal ou pelo celular
RT_PATH = os.path.join(DATA_DIR, "rt.json")
LOG_PATH = os.path.join(DATA_DIR, "server.log")
STATIC = os.path.join(BASE, "static")
CHANNEL_DIR = os.path.join(BASE, "roku-channel")



def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{threading.get_ident()}.tmp"   # um temporário por thread
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


CONFIG = load_json(CONFIG_PATH, {})

lock = threading.Lock()
state = {"running": False, "step": "", "done": 0, "total": 0, "error": None}


def _logger():
    os.makedirs(DATA_DIR, exist_ok=True)
    lg = logging.getLogger("watchlist")
    if not lg.handlers:
        h = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(threadName)s: %(message)s"))
        lg.addHandler(h)
        lg.setLevel(logging.INFO)
    return lg


log = _logger()


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
