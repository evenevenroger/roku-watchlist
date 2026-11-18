import json
import os
import tempfile
import unittest
from unittest import mock

from watchlist import data


class LocalListTests(unittest.TestCase):
    def test_keeps_file_order_and_drops_repeats(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "teste.json"), "w", encoding="utf-8") as f:
                json.dump({"items": [{"imdb": "tt2"}, {"imdb": "tt1"}, {"imdb": "tt2"}, {"imdb": "tt3"}]}, f)
            found = [{"id": "tt1"}, {"id": "tt2"}]        # tt3 sumiu do IMDb
            with mock.patch.object(data, "LOCAL_LISTS_DIR", folder), \
                 mock.patch.object(data, "fetch_titles", return_value=found) as fetch:
                items = data.fetch_local_list("teste")
        fetch.assert_called_once_with(["tt2", "tt1", "tt3"])
        self.assertEqual([t["id"] for t in items], ["tt2", "tt1"])

    def test_abraccine_file_has_100_distinct_titles(self):
        with open(os.path.join(data.LOCAL_LISTS_DIR, "abraccine.json"), encoding="utf-8") as f:
            items = json.load(f)["items"]
        self.assertEqual([i["pos"] for i in items], list(range(1, 101)))
        self.assertEqual(len({i["imdb"] for i in items}), 100)


if __name__ == "__main__":
    unittest.main()
