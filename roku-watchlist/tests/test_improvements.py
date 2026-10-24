"""Regressões das melhorias de conexão, preferências, sincronização e ZIP."""
import concurrent.futures
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
import zipfile

import requests

from watchlist import common, data, feed, preferences, roku, server


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        p = patch.object(preferences, "PATH", str(Path(self.temp.name) / "preferences.json"))
        p.start()
        self.addCleanup(p.stop)

    def test_persist_and_merge_two_devices_without_losing_fields(self):
        preferences.update_preferences({"lists": {"watchlist": {"sort": 7, "genre": "Drama"}}})
        preferences.update_preferences({"lists": {"watchlist": {"focus_id": "tt123", "dur": 2}}})
        saved = preferences.get_preferences()["lists"]["watchlist"]
        self.assertEqual(saved, {"sort": 7, "genre": "Drama", "focus_id": "tt123", "dur": 2})
        self.assertEqual(json.loads(Path(preferences.PATH).read_text(encoding="utf-8"))["revision"], 2)

    def test_global_unseen_propagates_and_explicit_list_override_wins(self):
        preferences.update_preferences({"lists": {"watchlist": {"seen": 0}}})
        preferences.update_preferences({"unseen": True})
        self.assertEqual(preferences.get_preferences()["lists"]["watchlist"]["seen"], 1)
        preferences.update_preferences({"lists": {"watchlist": {"seen": 0}}})
        self.assertEqual(preferences.get_preferences()["lists"]["watchlist"]["seen"], 0)

    def test_concurrent_writes_keep_all_lists(self):
        def save(n):
            preferences.update_preferences({"lists": {f"ls{n}": {"sort": n % 9}}})
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(save, range(24)))
        saved = preferences.get_preferences()
        self.assertEqual(len(saved["lists"]), 24)
        self.assertEqual(saved["revision"], 24)

    def test_invalid_patch_does_not_change_saved_preferences(self):
        preferences.update_preferences({"unseen": True})
        before = Path(preferences.PATH).read_bytes()
        for invalid in ({"lists": {"watchlist": {"sort": 99}}}, {"unseen": "yes"},
                        {"lists": {"watchlist": {"sort": True}}}, {"lists": {"../bad": {}}}):
            with self.assertRaises(ValueError):
                preferences.update_preferences(invalid)
        self.assertEqual(before, Path(preferences.PATH).read_bytes())


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "cache.json")
        self.old_state = dict(data.state)
        data.state.clear()
        data.state.update(running=False)
        self.addCleanup(self.restore_state)
        self.title = {"id": "tt1", "title": "Teste", "year": 2020}
        common.save_json(self.path, {"titles": {"tt1": self.title}, "lists": {"watchlist": ["tt1"]},
                                    "offers": {"tt1": {"ts": time.time(), "offers": []}}})
        for p in (patch.object(data, "CACHE_PATH", self.path),
                  patch.object(data, "CONFIG", {"auto_lists": False, "lists": [{"id": "watchlist", "name": "Watchlist"}]}),
                  patch.object(data, "fetch_rated", return_value=[]),
                  patch.object(data, "log"),
                  patch.object(data, "fetch_list", return_value=[self.title]),
                  patch.object(data, "fetch_english_titles", return_value={}),
                  patch.object(data, "sync_tv_awards"),
                  patch.object(data, "sync_series_runtimes", return_value=({}, {"failed": 0}))):
            p.start()
            self.addCleanup(p.stop)

    def restore_state(self):
        data.state.clear()
        data.state.update(self.old_state)

    def test_success_records_full_update(self):
        data.sync()
        cache = common.load_json(self.path, {})
        self.assertEqual(data.state["outcome"], "success")
        self.assertEqual(cache["full_synced_at"], cache["synced_at"])
        self.assertFalse(data.state["running"])

    def test_preserved_list_is_partial_not_success(self):
        with patch.object(data, "fetch_list", side_effect=RuntimeError("offline")):
            data.sync()
        cache = common.load_json(self.path, {})
        self.assertEqual(data.state["outcome"], "partial")
        self.assertEqual(cache["lists"]["watchlist"], ["tt1"])
        self.assertTrue(cache["sync_incomplete"])
        self.assertNotIn("full_synced_at", cache)

    def test_imdb_failure_is_failed_and_preserves_titles(self):
        with patch.object(data, "fetch_rated", side_effect=RuntimeError("offline")):
            data.sync()
        cache = common.load_json(self.path, {})
        self.assertEqual(data.state["outcome"], "failed")
        self.assertEqual(cache["titles"]["tt1"], self.title)

    def test_justwatch_block_is_partial_and_keeps_old_offers(self):
        with patch.object(data, "jw_lookup", side_effect=data.JustWatchUnavailable("HTTP 403")):
            data.sync(force_offers=True)
        cache = common.load_json(self.path, {})
        self.assertEqual(cache["sync_result"]["outcome"], "partial")
        self.assertIn("tt1", cache["offers"])
        self.assertTrue(cache["offers_incomplete"])

    def test_sync_reserved_before_worker_starts(self):
        with patch.object(data.threading, "Thread") as thread:
            self.assertTrue(data.start_sync())
            self.assertTrue(data.state["running"])
            self.assertFalse(data.start_sync())
            thread.assert_called_once()


class PackageTests(unittest.TestCase):
    def setUp(self):
        for p in (patch.object(feed, "lan_ip", return_value="192.168.68.101"),
                  patch.object(feed, "server_port", return_value=8790),
                  patch.object(feed.requests, "Session")):
            mock = p.start()
            self.addCleanup(p.stop)
            if hasattr(mock, "return_value") and "Session" in str(p.attribute):
                self.session = mock.return_value.__enter__.return_value
                self.session.get.return_value.json.return_value = {"app": "minha-watchlist"}

    def test_zip_has_only_channel_files_and_resolved_addresses(self):
        with zipfile.ZipFile(io.BytesIO(feed.build_channel_zip("evil.example:99"))) as package:
            names = package.namelist()
            self.assertEqual(len(names), len(set(names)))
            self.assertFalse(any("out/" in n or "/." in n for n in names))
            self.assertIn("components/Preferences.brs", names)
            config = package.read("components/config.brs")
            self.assertIn(b"http://192.168.68.101:8790", config)
            self.assertNotIn(b"__SERVER", config)
            self.assertNotIn(b"evil.example", config)
            self.assertIsNone(package.testzip())

    def test_refuses_loopback_and_wrong_application(self):
        with patch.object(feed, "lan_ip", return_value="127.0.0.1"):
            with self.assertRaises(ValueError):
                feed.build_channel_zip()
        self.session.get.return_value.json.return_value = {"app": "other"}
        with self.assertRaises(ValueError):
            feed.build_channel_zip()

    def test_environment_port_is_used(self):
        with patch.dict(os.environ, {"PORT": "9876"}):
            self.assertEqual(common.server_port(), 9876)

    def test_refuses_missing_script_referenced_by_component(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("manifest", "source/main.brs", "components/config.brs", "components/MainScene.xml", "components/ApiTask.xml"):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('<component name="Test"><script uri="pkg:/components/Missing.brs" /></component>'
                                  if name.endswith(".xml") else "", encoding="utf-8")
            with patch.object(feed, "CHANNEL_DIR", directory), self.assertRaisesRegex(ValueError, "Script ausente"):
                feed.build_channel_zip()


class ConnectionTests(unittest.TestCase):
    def test_offline_status_is_not_reported_connected(self):
        with patch.object(roku, "_health", {"at": 0, "value": None}), \
                patch.object(roku, "probe_roku", return_value=None):
            self.assertFalse(roku.roku_health()["connected"])

    def test_device_identity_is_verified(self):
        with patch.object(roku, "CONFIG", {"roku_serial": "expected"}), patch.object(roku.requests, "Session") as factory:
            response = factory.return_value.__enter__.return_value.get.return_value
            response.content = b"<device-info><serial-number>other</serial-number></device-info>"
            self.assertIsNone(roku.probe_roku("192.168.1.2"))
            response.content = b"<device-info><serial-number>expected</serial-number></device-info>"
            self.assertTrue(roku.probe_roku("192.168.1.2")["connected"])
            self.assertIsNone(roku.probe_roku("127.0.0.1"))

    def test_discovery_updates_ip_when_old_address_fails(self):
        hit = {"connected": True, "ip": "192.168.1.9", "serial": "expected", "name": "Roku", "error": None}
        with patch.object(roku, "CONFIG", {"roku_ip": "192.168.1.8", "roku_serial": "expected"}) as config, \
                patch.object(roku, "_health", {"at": 0, "value": None}), \
                patch.object(roku, "probe_roku", side_effect=[None, hit]), \
                patch.object(roku, "discover_roku", return_value=hit["ip"]), patch.object(roku, "save_json"):
            self.assertTrue(roku.roku_health(refresh=True)["connected"])
            self.assertEqual(config["roku_ip"], hit["ip"])


class HttpTests(unittest.TestCase):
    def test_preferences_and_bad_json_over_http(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(preferences, "PATH", str(Path(directory) / "prefs.json")):
            httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            worker = threading.Thread(target=httpd.serve_forever, daemon=True)
            worker.start()
            try:
                url = f"http://127.0.0.1:{httpd.server_port}"
                response = requests.post(url + "/api/preferences", json={"lists": {"watchlist": {"sort": 7}}}, timeout=3)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(requests.get(url + "/api/preferences", timeout=3).json()["lists"]["watchlist"]["sort"], 7)
                self.assertEqual(requests.post(url + "/api/preferences", data="{bad", timeout=3).status_code, 400)
                self.assertEqual(requests.post(url + "/api/preferences", json={"unseen": 3}, timeout=3).status_code, 400)
            finally:
                httpd.shutdown()
                httpd.server_close()
                worker.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
