"""Servidor web: página do celular, API do canal e sincronização automática."""
import gzip
import json
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .common import CACHE_PATH, CONFIG, STATIC, lan_ip, load_json, log, state
from .data import build_payload, sync
from .feed import build_channel_zip, record_play, roku_feed, roku_home, roku_list, roku_search
from .roku import KEYS, play_link, roku_post
from .rottentomatoes import rt_worker


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        gz = len(body) > 2048 and "gzip" in (self.headers.get("Accept-Encoding") or "")
        if gz:
            body = gzip.compress(body, 6)
        self.send_response(code)
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except Exception:  # noqa: BLE001 — registra e segue atendendo
            log.exception("erro ao atender %s", getattr(self, "path", "?"))

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/log":
            from .common import LOG_PATH
            try:
                with open(LOG_PATH, encoding="utf-8") as f:
                    tail = f.readlines()[-200:]
            except OSError:
                tail = []
            return self.send(200, "".join(tail).encode(), "text/plain; charset=utf-8")
        if path in ("/", "/index.html"):
            with open(os.path.join(STATIC, "index.html"), "rb") as f:
                return self.send(200, f.read(), "text/html; charset=utf-8")
        if path == "/api/data":
            return self.send(200, build_payload())
        if path == "/api/status":
            return self.send(200, {**state, "app": "minha-watchlist"})   # o canal reconhece o PC por aqui
        if path.startswith("/api/roku"):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            arg = lambda k: (q.get(k) or [""])[0]   # noqa: E731
            if path == "/api/roku/list":
                return self.send(200, roku_list(arg("id"), arg("v")))
            if path == "/api/roku/search":
                return self.send(200, roku_search(arg("q")))
            fmt = int(arg("fmt") or 1)
            if fmt >= 4:                            # canal build 12+: só os cartões da tela inicial
                return self.send(200, roku_home(arg("v")))
            return self.send(200, roku_feed(fmt, arg("v")))
        if path == "/roku-channel.zip":
            return self.send(200, build_channel_zip(self.headers.get("Host")),
                             "application/zip")
        self.send(404, {"error": "não encontrado"})

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/sync":
            force = bool(self.body().get("force"))
            threading.Thread(target=sync, args=(force,), daemon=True).start()
            return self.send(200, {"ok": True})
        if path == "/api/play":
            b = self.body()
            ok, err = play_link(b.get("roku") or "", b.get("title") or "",
                                b.get("title_pt"), b.get("type"), b.get("year"))
            if ok and b.get("id"):
                record_play(b["id"])
            return self.send(200, {"ok": ok, "error": err})
        if path == "/api/play_title":
            # usado pelo canal do Roku: manda só o id e o serviço
            b = self.body()
            t = next((x for x in build_payload()["titles"] if x["id"] == b.get("id")), None)
            m = t and next((m for m in t["mine"] if m["service"] == b.get("service")), None)
            if not m:
                return self.send(404, {"ok": False, "error": "título não encontrado"})
            ok, err = play_link(m["roku"] or "", t.get("original") or t["title"],
                                t["title"], t.get("type"), t.get("year"))
            if ok:
                record_play(t["id"])
            return self.send(200, {"ok": ok, "error": err})
        if path == "/api/key":
            k = self.body().get("key")
            if k not in KEYS:
                return self.send(400, {"ok": False, "error": "tecla inválida"})
            ok, err = roku_post(f"keypress/{k}")
            return self.send(200, {"ok": ok, "error": err})
        self.send(404, {"error": "não encontrado"})


def keep_awake():
    """Pede ao Windows para não dormir enquanto o servidor roda e o notebook está na
    tomada (como um player de vídeo faz). A tela apaga normalmente; na bateria, libera."""
    if sys.platform != "win32":
        return
    import ctypes

    class PowerStatus(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                    ("BatteryLifePercent", ctypes.c_byte), ("SystemStatusFlag", ctypes.c_byte),
                    ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]

    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
    k32 = ctypes.windll.kernel32
    holding = None
    while True:
        st = PowerStatus()
        on_ac = bool(k32.GetSystemPowerStatus(ctypes.byref(st))) and st.ACLineStatus == 1
        if on_ac != holding:
            flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on_ac else 0)
            k32.SetThreadExecutionState(flags)
            log.info("manter acordado: %s", "sim (na tomada)" if on_ac else "não (na bateria)")
            holding = on_ac
        time.sleep(60)


def auto_sync():
    # sincroniza ao abrir (se o cache tiver mais de 1 dia) e depois a cada 24 h;
    # se a última ficou incompleta (JustWatch bloqueou), tenta de novo após 2 h
    while True:
        c = load_json(CACHE_PATH, {})
        age = time.time() - (c.get("synced_at") or 0)
        retry = c.get("offers_incomplete") and time.time() - (c.get("sync_attempt_at") or 0) > 7200
        if age > 86400 or retry:
            sync()
        time.sleep(1800)


def main():
    if sys.stdout:   # com pythonw (início automático, sem janela) não há saída
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    port = int(os.environ.get("PORT") or CONFIG.get("port", 8765))
    threading.Thread(target=auto_sync, name="sync", daemon=True).start()
    threading.Thread(target=rt_worker, name="rt", daemon=True).start()
    threading.Thread(target=keep_awake, name="awake", daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    log.info("servidor no ar na porta %s", port)
    print(f"Watchlist → Roku rodando:\n  neste PC:  http://localhost:{port}\n"
          f"  no celular (mesmo Wi-Fi):  http://{lan_ip()}:{port}\nCtrl+C para parar.")
    srv.serve_forever()
