import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from watchlist import feed, tv_awards as tv


def node(event, category, won=True, year=2024):
    return {"isWinner": won, "award": {"event": {"id": event, "text": "Award"},
                                       "category": {"text": category}, "year": year, "text": "Award"}}


def connection(nodes, after=None):
    return {"awardNominations": {"edges": [{"node": n} for n in nodes],
                                 "pageInfo": {"hasNextPage": after is not None, "endCursor": after}}}


class TVAwardsTests(unittest.TestCase):
    series = {"id": "tt1", "type": "tvSeries", "title": "Show", "original": "Show"}

    def test_requested_categories_and_historical_names(self):
        cases = {
            "ev0000223": ["Outstanding Drama Series", "Best Dramatic Series", "Outstanding Drama Series – Continuing",
                          "Outstanding Comedy Series", "Best Comedy Series", "Best Situation Comedy",
                          "Outstanding Drama/Comedy – Limited Episodes", "Outstanding Limited Series",
                          "Outstanding Miniseries", "Outstanding Miniseries or Movie", "Outstanding Limited or Anthology Series"],
            "ev0000292": ["Best Television Series – Drama", "Best Television Series – Musical or Comedy",
                          "Best Miniseries or Television Film", "Best Television Limited Series, Anthology Series, or Motion Picture Made for Television",
                          "Best Television Series", "Best Television Program"],
            "ev0000123": ["Drama Production", "Drama Series", "Drama Series or Serial", "Comedy Series", "Situation Comedy",
                          "Comedy – Programme or Series", "Comedy Programme", "Scripted Comedy", "Drama Serial", "Mini-Series",
                          "Limited Drama", "Foreign Television Programme", "International Programme", "International"],
            "ev0002032": ["Best Drama Series", "Best Comedy Series", "Best Movie/Miniseries", "Best Limited Series"],
            "ev0000527": ["Entertainment"],
        }
        for event, categories in cases.items():
            for category in categories:
                with self.subTest(event=event, category=category):
                    self.assertIn(tv.EVENTS[event], tv.select_entries([node(event, category)], self.series))

    def test_individual_and_unrequested_program_awards_do_not_qualify(self):
        nodes = [node("ev0000223", "Outstanding Lead Actor in a Drama Series"),
                 node("ev0000223", "Outstanding Writing for a Comedy Series"),
                 node("ev0000223", "Outstanding Animated Program"),
                 node("ev0000292", "Best Performance by an Actor in a Television Series - Drama"),
                 node("ev0000123", "Best Female Performance in a Comedy Programme"),
                 node("ev0002032", "Best Supporting Actor in a Drama Series"),
                 node("ev0002032", "Most Exciting New Series"), node("ev0000527", "Documentary and Education")]
        self.assertEqual(tv.select_entries(nodes, self.series), {})

    def test_only_bafta_international_nominations_qualify(self):
        nodes = [node("ev0000223", "Outstanding Drama Series", False), node("ev0000292", "Best Television Series - Drama", False),
                 node("ev0000123", "Best Drama Series", False), node("ev0002032", "Best Drama Series", False),
                 node("ev0000123", "Best International Series", False)]
        selected = tv.select_entries(nodes, self.series)
        self.assertEqual(set(selected), {"bafta_tv"})
        strip = tv.award_fields(selected)["strips"]
        self.assertEqual(len(strip), 1)
        self.assertFalse(strip[0]["w"])
        self.assertIn("indicado", strip[0]["t"])

    def test_priority_uses_one_strip_even_when_lower_award_is_newer(self):
        entries = tv.select_entries([node("ev0000223", "Outstanding Drama Series", year=2000),
                                     node("ev0000292", "Best Television Series - Drama", year=2026),
                                     node("ev0000123", "Drama Series"), node("ev0002032", "Best Drama Series"),
                                     node("ev0000527", "Entertainment")], self.series)
        for expected in tv.PRIORITY:
            strips = tv.award_fields(entries)["strips"]
            self.assertEqual(len(strips), 1)
            self.assertEqual(strips[0]["award"], expected)
            entries.pop(expected)
        self.assertEqual(tv.award_fields(entries)["strips"], [])

    def test_bafta_international_nomination_precedes_critics_winner(self):
        entries = tv.select_entries([node("ev0000123", "International", False),
                                     node("ev0000133", "Best Drama Series")], self.series)
        self.assertEqual(tv.award_fields(entries)["strips"][0]["award"], "bafta_tv")

    def test_miniseries_and_feature_films_are_separate(self):
        mini = {**self.series, "type": "tvMiniSeries"}
        movie = {**self.series, "type": "movie"}
        award = node("ev0000123", "Drama Series or Serial")
        self.assertEqual(tv.select_entries([award], mini)["bafta_tv"][0]["c"], "Minissérie")
        self.assertEqual(tv.select_entries([award], self.series)["bafta_tv"][0]["c"], "Drama")
        self.assertEqual(tv.select_entries([award], movie), {})

    def test_full_pagination_finds_award_after_first_page(self):
        first = {"id": "tt1", **connection([node("ev0000223", "Outstanding Lead Actor in a Drama Series")], "page2")}
        second = {"id": "tt1", **connection([node("ev0000223", "Outstanding Drama Series")])}
        with patch.object(tv, "imdb_query", side_effect=[{"titles": [first]}, {"titles": [second]}]) as query:
            data = tv.fetch_nominations(["tt1"])
        self.assertEqual(query.call_args_list[1].args[1]["after"], "page2")
        self.assertIn("emmy", tv.select_entries(data["tt1"], self.series))

    def test_missing_title_and_stuck_cursor_fail_instead_of_marking_no_awards(self):
        with patch.object(tv, "imdb_query", return_value={"titles": []}), self.assertRaises(RuntimeError):
            tv.fetch_nominations(["tt1"])
        page = {"id": "tt1", **connection([], "stuck")}
        with patch.object(tv, "imdb_query", return_value={"titles": [page]}), self.assertRaises(RuntimeError):
            tv.fetch_nominations(["tt1"])

    def test_peabody_blank_category_needs_official_entertainment_evidence(self):
        raw = [node("ev0000527", "", year=2024)]
        self.assertEqual(tv.select_entries(raw, self.series), {})
        profile = {"category": "Entertainment", "winner": True, "year": 2023, "url": "https://peabodyawards.com/award-profile/show/"}
        self.assertIn("peabody", tv.select_entries(raw, self.series, [profile]))
        self.assertEqual(tv.select_entries(raw, self.series, [{**profile, "category": "Documentary"}]), {})
        self.assertEqual(tv.select_entries(raw, self.series, [{**profile, "winner": False}]), {})
        self.assertEqual(tv.select_entries(raw, self.series, [{**profile, "year": 2000}]), {})

    def test_official_profile_must_match_title_and_breadcrumb_category(self):
        text = '<h1 class="profile__title">Show</h1><span class="profile__type">Winner</span><span class="profile__year">2023</span>'
        schema = {"@graph": [{"@type": "BreadcrumbList", "itemListElement": [
            {"name": "Entertainment", "item": "https://peabodyawards.com/categories/entertainment/"}]}]}
        text += '<script type="application/ld+json">' + json.dumps(schema) + '</script>'
        profile = tv.parse_peabody_profile(text, "official", self.series)
        self.assertEqual(profile["category"], "Entertainment")
        self.assertIsNone(tv.parse_peabody_profile(text.replace('>Show<', '>Other<'), "official", self.series))
        self.assertEqual(tv.parse_peabody_profile(text.replace('BreadcrumbList', 'Other'), "official", self.series)["category"], "Other")

    def test_network_failure_does_not_replace_previous_cache(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(tv, "PATH", str(Path(directory) / "tv.json")):
            old = {"titles": {"tt1": {"version": 0, "checked_at": 0, "entries": {"emmy": [{"c": "Drama", "w": True, "y": 2024}]}}}}
            Path(tv.PATH).write_text(json.dumps(old), encoding="utf-8")
            before = Path(tv.PATH).read_bytes()
            with patch.object(tv, "fetch_nominations", side_effect=RuntimeError("offline")), self.assertRaises(RuntimeError):
                tv.sync_tv_awards([self.series])
            self.assertEqual(before, Path(tv.PATH).read_bytes())

    def test_series_uses_tv_strip_instead_of_movie_awards(self):
        title = {**self.series, "tv_awards": tv.select_entries([node("ev0000223", "Outstanding Drama Series")], self.series),
                 "awards": {"oscar": [{"c": "Melhor filme", "w": True, "y": 2024}]}}
        self.assertEqual(feed.award_fields(title, "watchlist")["strips"][0]["award"], "emmy")
        movie = {"type": "movie", "awards": {"oscar": [{"c": "Melhor filme", "w": True, "y": 2024}],
                                              "cannes": [{"c": "Palma de Ouro", "w": True, "y": 2024}]}}
        self.assertEqual(len(feed.award_fields(movie, "watchlist")["strips"]), 2)


if __name__ == "__main__":
    unittest.main()
