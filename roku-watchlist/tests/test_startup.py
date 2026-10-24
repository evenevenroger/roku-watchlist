"""Verifica o início automático sem interromper o servidor de uso normal."""
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

import ensure_server


class StartupTests(unittest.TestCase):
    def test_healthy_server_is_not_started_twice(self):
        with patch.object(ensure_server, "healthy", return_value=True), \
                patch.object(ensure_server.subprocess, "Popen") as launch:
            self.assertFalse(ensure_server.ensure_server(9876))
            launch.assert_not_called()

    def test_other_application_on_port_is_not_replaced(self):
        with patch.object(ensure_server, "healthy", return_value=False), \
                patch.object(ensure_server.socket, "socket") as factory, \
                patch.object(ensure_server.subprocess, "Popen") as launch:
            factory.return_value.__enter__.return_value.connect_ex.return_value = 0
            with self.assertRaisesRegex(RuntimeError, "ocupada"):
                ensure_server.ensure_server(9876)
            launch.assert_not_called()

    def test_stopped_server_is_started_and_can_be_started_again(self):
        # Servidor descartável em porta própria; não acessa dados nem rede do Roku.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            (root / "config.json").write_text(json.dumps({"port": port}), encoding="utf-8")
            (root / "app.py").write_text(
                'from http.server import BaseHTTPRequestHandler, HTTPServer\n'
                'class Handler(BaseHTTPRequestHandler):\n'
                ' def do_GET(self):\n'
                '  body=b\'{"app":"minha-watchlist"}\'\n'
                '  self.send_response(200); self.end_headers(); self.wfile.write(body)\n'
                ' def log_message(self,*args): pass\n'
                f'HTTPServer(("127.0.0.1",{port}),Handler).serve_forever()\n', encoding="utf-8")
            real_launch = ensure_server.subprocess.Popen
            children = []

            def launch(*args, **kwargs):
                child = real_launch(*args, **kwargs)
                children.append(child)
                return child

            with patch.object(ensure_server, "BASE", root), \
                    patch.object(ensure_server.subprocess, "Popen", side_effect=launch):
                try:
                    self.assertTrue(ensure_server.ensure_server(port))
                    self.assertTrue(ensure_server.healthy(port))
                    self.assertFalse(ensure_server.ensure_server(port))
                    children[0].terminate()
                    children[0].wait(timeout=5)
                    self.assertTrue(ensure_server.ensure_server(port))
                    self.assertEqual(len(children), 2)
                    self.assertTrue(ensure_server.healthy(port))
                finally:
                    for child in children:
                        if child.poll() is None:
                            child.terminate()
                        child.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
