"""Regressões da fila de disponibilidade e da distinção entre espera e falha."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from watchlist import common, data, justwatch


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "cache.json")
        old = dict(data.state)
        self.addCleanup(lambda: (data.state.clear(), data.state.update(old)))
        data.state.clear()
        data.state.update(running=False)
        self.config = {"auto_lists": False, "offers_max_age_days": 3,
                       "jw_per_run": 500, "lists": [{"id": "watchlist", "name": "Watchlist"}]}
        for p in (patch.object(data, "CACHE_PATH", self.path),
                  patch.object(data, "CONFIG", self.config), patch.object(data, "log"),
                  patch.object(data, "fetch_rated", return_value=[]),
                  patch.object(data, "fetch_english_titles", return_value={}),
                  patch.object(data, "sync_tv_awards"),
                  patch.object(data, "sync_series_runtimes", return_value=({}, {"failed": 0}))):
            p.start()
            self.addCleanup(p.stop)

    def seed(self, count, fresh=False):
        titles = {f"tt{i:04}": {"id": f"tt{i:04}", "type": "movie", "title": f"Film {i}"} for i in range(count)}
        cache = {"titles": titles, "lists": {"watchlist": list(titles)}, "synced_at": time.time(),
                 "offers": {tid: {"ts": time.time() if fresh else 1, "offers": [], "old": True} for tid in titles}}
        common.save_json(self.path, cache)
        return cache

    def test_more_than_500_jobs_reaches_complete_without_a_two_hour_pause(self):
        cache = self.seed(501)
        with patch.object(data, "fetch_list", return_value=list(cache["titles"].values())), \
                patch.object(data, "jw_lookup", return_value={"found": False, "offers": []}) as lookup:
            data.sync()
        saved = common.load_json(self.path, {})
        self.assertEqual(lookup.call_count, 501)
        self.assertEqual(saved["sync_result"]["outcome"], "success")
        self.assertEqual(saved["offers_queue"], [])
        self.assertFalse(saved["offers_incomplete"])
        self.assertEqual(data.cache_status(saved)["pending_offers"], 0)
        self.assertEqual(data.state["done"], data.state["total"])

    def test_failure_stops_before_the_next_title_and_saves_recent_progress(self):
        cache = self.seed(3)
        with patch.object(data, "fetch_list", return_value=list(cache["titles"].values())), \
                patch.object(data, "jw_lookup", side_effect=[{"found": True, "offers": []}, justwatch.JustWatchUnavailable("HTTP 403")]) as lookup:
            data.sync()
        saved = common.load_json(self.path, {})
        self.assertEqual(lookup.call_count, 2)
        self.assertGreater(saved["offers"]["tt0000"]["ts"], 1)
        self.assertEqual(saved["offers"]["tt0001"], cache["offers"]["tt0001"])
        self.assertEqual(saved["offers_queue"], ["tt0001", "tt0002"])
        self.assertEqual(saved["sync_result"]["outcome"], "partial")
        self.assertIsNone(data.sync_action(saved))

    def test_restart_resumes_forced_queue_even_when_timestamps_are_fresh(self):
        cache = self.seed(3, fresh=True)
        cache["offers_queue"] = ["tt0001", "tt0002"]
        cache["sync_result"] = {"outcome": "running", "problems": []}
        common.save_json(self.path, cache)
        self.assertEqual(data.sync_action(cache), "offers")
        with patch.object(data, "fetch_list") as lists, \
                patch.object(data, "jw_lookup", return_value={"found": False, "offers": []}) as lookup:
            data.sync(offers_only=True)
        lists.assert_not_called()
        self.assertEqual([c.args[0]["id"] for c in lookup.call_args_list], ["tt0001", "tt0002"])
        saved = common.load_json(self.path, {})
        self.assertEqual(data.cache_status(saved)["outcome"], "success")
        self.assertEqual(saved["offers_queue"], [])

    def test_metadata_refresh_keeps_english_titles_and_posters(self):
        cache = self.seed(1, fresh=True)
        cache["titles"]["tt0000"].update(title_en="English title", poster_en="english.jpg", country_ids=["US"])
        common.save_json(self.path, cache)
        fresh = {"id": "tt0000", "type": "movie", "title": "Novo nome", "rating": 8.1}
        with patch.object(data, "fetch_list", return_value=[fresh]), \
                patch.object(data, "fetch_english_titles") as english:
            data.sync()
        saved = common.load_json(self.path, {})
        self.assertEqual(saved["titles"]["tt0000"]["title_en"], "English title")
        self.assertEqual(saved["titles"]["tt0000"]["poster_en"], "english.jpg")
        self.assertEqual(saved["titles"]["tt0000"]["title"], "Novo nome")
        english.assert_not_called()

    def test_legacy_pending_is_not_a_source_failure_and_ignores_unused_titles(self):
        cache = self.seed(1)
        cache.update(synced_at=time.time(), sync_incomplete=True, offers_incomplete=True,
                     sync_result={"outcome": "partial", "finished_at": time.time(),
                                  "problems": ["Faltam consultar 1 títulos; nova tentativa em 2 horas."]})
        cache["offers"]["unused"] = {"ts": 1}
        status = data.cache_status(cache)
        self.assertEqual(status["outcome"], "pending")
        self.assertEqual(status["coverage"]["pending"], 1)
        self.assertEqual(data.sync_action(cache), "offers")
        cache["offers"]["tt0000"]["ts"] = time.time()
        self.assertEqual(data.cache_status(cache)["outcome"], "success")
        self.assertFalse(data.cache_status(cache)["incomplete"])

    def test_offer_resume_does_not_postpone_daily_metadata_refresh(self):
        cache = self.seed(1, fresh=True)
        metadata_at = time.time() - 86399
        cache.update(synced_at=metadata_at, metadata_synced_at=metadata_at, offers_queue=["tt0000"])
        common.save_json(self.path, cache)
        with patch.object(data, "jw_lookup", return_value={"found": False, "offers": []}):
            data.sync(offers_only=True)
        saved = common.load_json(self.path, {})
        self.assertEqual(saved["metadata_synced_at"], metadata_at)
        self.assertGreater(saved["synced_at"], metadata_at)
        self.assertEqual(data.sync_action(saved, now=metadata_at + 86401), "full")

    def test_real_failure_retains_partial_status_and_two_hour_backoff(self):
        cache = self.seed(1, fresh=True)
        cache.update(synced_at=time.time(), sync_result={"outcome": "partial", "finished_at": time.time(),
                                                      "problems": ["Lista preservada sem atualizar: Séries"]})
        self.assertEqual(data.cache_status(cache)["outcome"], "partial")
        self.assertIsNone(data.sync_action(cache))
        self.assertEqual(data.sync_action(cache, now=time.time() + 7201), "full")

    def test_old_in_memory_failure_cannot_override_persisted_success(self):
        cache = self.seed(1, fresh=True)
        cache["sync_result"] = {"outcome": "success", "problems": []}
        common.save_json(self.path, cache)
        data.state.update(running=False, outcome="failed", problems=["stale failure"])
        self.assertEqual(data.sync_status()["outcome"], "success")
        self.assertEqual(data.sync_status()["problems"], [])

    def test_live_coverage_counts_work_since_the_last_checkpoint(self):
        cache = self.seed(3, fresh=True)
        cache.update(offers_queue=list(cache["titles"]), sync_result={"outcome": "running", "problems": [], "started_at": 123})
        common.save_json(self.path, cache)
        data.state.update(running=True, total=3, done=2, outcome="running", started_at=123)
        status = data.sync_status()
        self.assertEqual(status["pending_offers"], 1)
        self.assertEqual(status["coverage"]["fresh"], 2)


class ProviderTests(unittest.TestCase):
    def test_http_200_with_graphql_errors_is_never_saved_as_not_found(self):
        for payload in ({"errors": [{"message": "Unavailable"}], "data": None}, {"data": {}}, {"data": {"popularTitles": None}}):
            with self.subTest(payload=payload), patch.object(justwatch.time, "sleep"), \
                    patch.object(justwatch.requests, "post") as post:
                post.return_value.status_code = 200
                post.return_value.json.return_value = payload
                with self.assertRaises(justwatch.JustWatchUnavailable):
                    justwatch.jw_lookup({"id": "tt1", "title": "Show"})
                self.assertEqual(post.call_count, 3)

    def test_valid_empty_search_can_confirm_not_found(self):
        with patch.object(justwatch.time, "sleep"), patch.object(justwatch.requests, "post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {"data": {"popularTitles": {"edges": []}}}
            self.assertEqual(justwatch.jw_lookup({"id": "tt1", "title": "Show"}), {"found": False, "offers": []})


if __name__ == "__main__":
    unittest.main()
