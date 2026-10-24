"""Inicia a Watchlist sem janela se ela não estiver respondendo neste computador."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = Path(__file__).resolve().parent


def server_port():
    try:
        config = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        config = {}
    return int(os.environ.get("PORT") or config.get("port", 8790))


def healthy(port):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/api/status", timeout=2) as response:
            return json.loads(response.read(65536)).get("app") == "minha-watchlist"
    except (OSError, ValueError, AttributeError, urllib.error.URLError):
        return False


def ensure_server(port=None):
    """Retorna True se iniciou o servidor; False quando ele já estava saudável."""
    port = port or server_port()
    if healthy(port):
        return False
    with socket.socket() as connection:
        connection.settimeout(1)
        if connection.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError(f"A porta {port} está ocupada, mas a Watchlist não respondeu.")
    data = BASE / "data"
    data.mkdir(exist_ok=True)
    output = data / "startup-output.log"
    if output.exists() and output.stat().st_size > 1_000_000:
        output.replace(data / "startup-output.previous.log")
    # python.exe com CREATE_NO_WINDOW mantém os erros no log, sem abrir um console.
    python = Path(sys.executable).with_name("python.exe") if os.name == "nt" else Path(sys.executable)
    with output.open("a", encoding="utf-8") as stream:
        child = subprocess.Popen([str(python), "-X", "utf8", str(BASE / "app.py")], cwd=BASE,
                                 stdout=stream, stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if healthy(port):
            return True
        if child.poll() is not None:
            raise RuntimeError(f"O servidor encerrou ao iniciar (código {child.returncode}). Veja {output}.")
        time.sleep(0.25)
    raise RuntimeError("O servidor ainda não respondeu. A próxima verificação tentará novamente.")


def main():
    data = BASE / "data"
    data.mkdir(exist_ok=True)
    # O atalho e a tarefa podem disparar juntos: só um inicia o servidor.
    with (data / "startup.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return
        try:
            started = ensure_server()
            if started:
                with (data / "startup.log").open("a", encoding="utf-8") as stream:
                    stream.write(time.strftime("%Y-%m-%d %H:%M:%S") + " servidor iniciado automaticamente\n")
        except Exception as exc:
            with (data / "startup.log").open("a", encoding="utf-8") as stream:
                stream.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + str(exc) + "\n")
            raise


if __name__ == "__main__":
    main()
