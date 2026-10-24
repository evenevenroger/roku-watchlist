"""Prêmios de séries e minisséries: categorias de programa, sem prêmios individuais."""
import os
import re
import threading
import time
import unicodedata
import json
import html
import urllib.parse
import requests

from .common import DATA_DIR, load_json, save_json, state
from .imdb import imdb_query

PATH = os.path.join(DATA_DIR, "tv_awards.json")
SERIES_TYPES = {"tvSeries", "tvMiniSeries"}
PRIORITY = ("emmy", "golden_globe", "bafta_tv", "critics_choice", "peabody")
NAMES = {"emmy": "Emmy", "golden_globe": "Golden Globe", "bafta_tv": "BAFTA",
         "critics_choice": "Critics’ Choice", "peabody": "Peabody"}
EVENTS = {"ev0000223": "emmy", "ev0000292": "golden_globe", "ev0000123": "bafta_tv",
          "ev0002032": "critics_choice", "ev0000133": "critics_choice", "ev0000527": "peabody"}
VERSION = 4
MAX_AGE = 86400
_lock = threading.Lock()

# Perfis oficiais confirmados: resolvem grafia alternativa e resultados de busca incompletos.
PEABODY_PROFILE_HINTS = {
    "tt0106179": ("https://peabodyawards.com/award-profile/the-x-files/",),
    "tt3021686": ("https://peabodyawards.com/award-profile/the-honorable-woman/",),
    "tt2149175": ("https://peabodyawards.com/award-profile/the-americans/",
                  "https://peabodyawards.com/award-profile/the-americans-2018/"),
    "tt7016936": ("https://peabodyawards.com/award-profile/killing-eve/",),
}
PEABODY_TITLE_ALIASES = {"tt3021686": ("The Honorable Woman",)}
# O perfil de Killing Eve está classificado como News no site; o anúncio oficial
# coloca explicitamente a série entre os vencedores de Entertainment de 2018.
PEABODY_CATEGORY_CORRECTIONS = {
    ("https://peabodyawards.com/award-profile/killing-eve/", 2018):
    "https://peabodyawards.com/stories/entertainment-childrens-youth-winners-awarded/",
}


def normalize(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"mini[\s-]+series", "miniseries", text)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def aliases(*values):
    return {normalize(value) for value in values}


CATEGORIES = {
    "emmy": {
        "Drama": aliases("Outstanding Drama Series", "Best Dramatic Series", "Outstanding Dramatic Series",
                         "Outstanding Drama Series – Continuing", "Best Dramatic Series with Continuing Characters",
                         "Best Dramatic Show", "Best Dramatic Program", "Best Dramatic Anthology Series",
                         "Outstanding Program Achievement in the Field of Drama"),
        "Comédia": aliases("Outstanding Comedy Series", "Best Comedy Series", "Best Situation Comedy",
                           "Outstanding Comedy Series – Continuing", "Best Situation Comedy Series",
                           "Outstanding Program Achievement in the Field of Humor"),
        "Minissérie": aliases("Outstanding Drama/Comedy – Limited Episodes", "Outstanding Limited Series",
                              "Outstanding Miniseries", "Outstanding Miniseries or Movie",
                              "Outstanding Limited or Anthology Series"),
    },
    "golden_globe": {
        "Drama": aliases("Best Television Series – Drama", "Best Television Series, Drama"),
        "Comédia": aliases("Best Television Series – Musical or Comedy", "Best Television Series – Comedy or Musical"),
        "Minissérie": aliases("Best Miniseries or Television Film", "Best Miniseries or Motion Picture Made for Television",
                              "Best Television Limited Series or Motion Picture Made for Television",
                              "Best Television Limited Series, Anthology Series, or Motion Picture Made for Television"),
        "Série": aliases("Best Television Series", "Best Television Program"),
    },
    "bafta_tv": {
        "Drama": aliases("Drama Production", "Drama Series", "Drama Series or Serial", "Outstanding Drama Series"),
        "Comédia": aliases("Comedy Series", "Situation Comedy", "Comedy – Programme or Series", "Comedy Programme", "Scripted Comedy"),
        "Minissérie": aliases("Drama Series or Serial", "Drama Serial", "Mini-Series", "Limited Drama"),
        "Internacional": aliases("Foreign Television Programme", "International Programme", "International", "International Series"),
    },
    "critics_choice": {
        "Drama": aliases("Best Drama Series"),
        "Comédia": aliases("Best Comedy Series"),
        "Minissérie": aliases("Best Movie/Miniseries", "Best Limited Series"),
    },
    "peabody": {"Entretenimento": aliases("Entertainment")},
}


def classify(group, category, kind):
    key = normalize(category)
    keys = {key, key.removeprefix("best ")}
    for label, accepted in CATEGORIES[group].items():
        if keys & accepted:
            # O BAFTA usou o mesmo nome para séries e seriados limitados.
            if group == "bafta_tv" and key.removeprefix("best ") == "drama series or serial":
                return "Minissérie" if kind == "tvMiniSeries" else "Drama"
            return label
    return None


def select_entries(nodes, title, peabody_profiles=()):
    if title.get("type") not in SERIES_TYPES:
        return {}
    entries = {}
    for node in nodes:
        award = node.get("award") or {}
        group = EVENTS.get((award.get("event") or {}).get("id"))
        if not group:
            continue
        raw_category = (award.get("category") or {}).get("text") or ""
        label = classify(group, raw_category, title["type"])
        if type(node.get("isWinner")) is not bool:
            raise RuntimeError("IMDb não informou se o prêmio foi vencido ou indicado.")
        won = node["isWinner"]
        official = None
        if group == "peabody" and not label and won:
            official = next((profile for profile in peabody_profiles
                             if profile["category"] == "Entertainment" and profile["winner"]
                             and award.get("year") in (profile["year"], profile["year"] + 1)), None)
            if official:
                label = "Entretenimento"
        if not label or (not won and not (group == "bafta_tv" and label == "Internacional")):
            continue
        entry = {"c": label, "y": award.get("year"), "w": won,
                 "source_category": raw_category, "event": award["event"]["id"]}
        if official:
            entry.update(official_source=official["url"], official_year=official["year"])
            if official.get("category_source"):
                entry["category_source"] = official["category_source"]
        if entry not in entries.setdefault(group, []):
            entries[group].append(entry)
    return entries


def parse_peabody_profile(text, url, title):
    """Valida o nome, o resultado e a categoria no próprio perfil oficial."""
    def field(tag, cls):
        match = re.search(r'<' + tag + r'\b[^>]*class="[^"\n]*\b' + cls + r'\b[^"\n]*"[^>]*>(.*?)</' + tag + '>', text, re.S)
        return html.unescape(re.sub(r"<[^>]*>", "", match.group(1))).strip() if match else ""
    name = field("h1", "profile__title")
    names = {normalize(title.get("original")), normalize(title.get("title"))} - {""}
    names.update(normalize(name) for name in PEABODY_TITLE_ALIASES.get(title["id"], ()))
    if normalize(name) not in names and normalize(name).removeprefix("the ") not in {n.removeprefix("the ") for n in names}:
        return None
    year = field("span", "profile__year")
    if not year.isdigit():
        return None
    category = "Other"
    for raw in re.findall(r'<script\b[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', text, re.S):
        schema = json.loads(raw)
        for item in schema.get("@graph", [schema]):
            if item.get("@type") == "BreadcrumbList":
                for crumb in item.get("itemListElement", []):
                    if crumb.get("name") == "Entertainment" and "/categories/entertainment/" in crumb.get("item", ""):
                        category = "Entertainment"
    result = {"title": name, "year": int(year), "winner": field("span", "profile__type").lower() == "winner",
              "category": category, "url": url}
    correction = PEABODY_CATEGORY_CORRECTIONS.get((url, int(year)))
    if correction:
        result.update(category="Entertainment", category_source=correction)
    return result


def peabody_profiles(title, nodes, previous):
    unknown_years = {node["award"]["year"] for node in nodes if node.get("isWinner") is True
                     and (node.get("award") or {}).get("event", {}).get("id") == "ev0000527"
                     and not classify("peabody", ((node["award"].get("category") or {}).get("text") or ""), title["type"])}
    if not unknown_years:
        return previous or {"profiles": [], "years": [], "checked_at": time.time()}
    hints = PEABODY_PROFILE_HINTS.get(title["id"], ())
    stale_hints = bool(set(hints) - set((previous or {}).get("urls_checked", [])))
    if previous and not stale_hints and (previous.get("profiles") or previous.get("quoted_search")) and unknown_years.issubset(previous.get("years", [])) and time.time() - previous.get("checked_at", 0) < 30 * 86400:
        return previous
    query = title.get("original") or title["title"]
    response = requests.get("https://peabodyawards.com/", params={"s": '"' + query + '"', "post_type": "award-profile"}, timeout=20)
    response.raise_for_status()
    urls = sorted(set(html.unescape(url) for url in re.findall(r'https://peabodyawards.com/award-profile/[^"<>\s]+', response.text)))
    urls = sorted(set(urls) | set(hints))
    profiles = []
    for url in urls:
        if urllib.parse.urlsplit(url).hostname != "peabodyawards.com":
            continue
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        profile = parse_peabody_profile(response.text, url, title)
        if profile:
            profiles.append(profile)
    return {"profiles": profiles, "years": sorted(unknown_years), "checked_at": time.time(), "quoted_search": True, "urls_checked": urls}


Q_NOMINATIONS = """query($ids:[ID!]!,$events:[ID!],$after:ID){titles(ids:$ids){id
 awardNominations(first:250,after:$after,filter:{events:$events}){
 pageInfo{hasNextPage endCursor} edges{node{isWinner award{text year category{text} event{id text}}}}}}} """


def fetch_nominations(ids):
    data = imdb_query(Q_NOMINATIONS, {"ids": ids, "events": list(EVENTS), "after": None})
    titles = {title["id"]: title for title in data["titles"] if title}
    if set(titles) != set(ids):
        raise RuntimeError("IMDb não devolveu todos os títulos ao consultar prêmios de TV.")
    result = {}
    for tid, title in titles.items():
        connection = title.get("awardNominations")
        if not connection or "pageInfo" not in connection:
            raise RuntimeError("IMDb devolveu uma consulta incompleta de prêmios de TV.")
        nodes = [edge["node"] for edge in connection["edges"]]
        cursors = set()
        while connection["pageInfo"]["hasNextPage"]:
            cursor = connection["pageInfo"]["endCursor"]
            if not cursor or cursor in cursors:
                raise RuntimeError("Paginação de prêmios de TV não avançou.")
            cursors.add(cursor)
            page = imdb_query(Q_NOMINATIONS, {"ids": [tid], "events": list(EVENTS), "after": cursor})
            if not page["titles"] or not page["titles"][0] or page["titles"][0]["id"] != tid:
                raise RuntimeError("Página de prêmios de TV ausente.")
            connection = page["titles"][0]["awardNominations"]
            nodes.extend(edge["node"] for edge in connection["edges"])
        result[tid] = nodes
    return result


def read_cache():
    with _lock:
        return load_json(PATH, {"titles": {}})


def sync_tv_awards(titles, force=False):
    titles = {title["id"]: title for title in titles if title.get("type") in SERIES_TYPES}
    cached = read_cache().get("titles", {})
    todo = [tid for tid in sorted(titles) if force or cached.get(tid, {}).get("version") != VERSION
            or time.time() - cached.get(tid, {}).get("checked_at", 0) >= MAX_AGE]
    for offset in range(0, len(todo), 10):
        ids = todo[offset:offset + 10]
        state["step"] = f"Consultando prêmios de séries ({offset}/{len(todo)})"
        fetch = [tid for tid in ids if force or "nominations" not in cached.get(tid, {})
                 or time.time() - cached[tid].get("checked_at", 0) >= MAX_AGE]
        raw = fetch_nominations(fetch) if fetch else {}
        records = {}
        for tid in ids:
            nominations = raw[tid] if tid in raw else cached[tid]["nominations"]
            validation = peabody_profiles(titles[tid], nominations, cached.get(tid, {}).get("peabody_validation"))
            records[tid] = {"version": VERSION, "checked_at": time.time() if tid in raw else cached[tid]["checked_at"],
                            "entries": select_entries(nominations, titles[tid], validation["profiles"]),
                            "nominations": nominations, "peabody_validation": validation}
        with _lock:
            current = load_json(PATH, {"titles": {}})
            current.setdefault("titles", {}).update(records)
            save_json(PATH, current)
    return {"checked": len(todo), "total": len(titles)}


def award_fields(entries):
    lines = []
    for group in PRIORITY:
        for entry in sorted(entries.get(group, []), key=lambda x: (-(x.get("y") or 0), x["c"])):
            result = "venceu" if entry["w"] else "indicado"
            lines.append(f"{NAMES[group]} {entry.get('y') or ''}: {entry['c']} ({result})")
    strips = []
    for group in PRIORITY:
        eligible = [entry for entry in entries.get(group, [])
                    if entry["w"] or (group == "bafta_tv" and entry["c"] == "Internacional")]
        if not eligible:
            continue
        categories = list(CATEGORIES[group])
        chosen = min(eligible, key=lambda x: (not x["w"], categories.index(x["c"]), -(x.get("y") or 0)))
        label = "indicado" if not chosen["w"] else chosen["c"]
        if label in ("Entretenimento", "Série") or group in ("golden_globe", "critics_choice"):
            text = NAMES[group]
        elif label == "Internacional":
            text = NAMES[group] + " · Internac."
        else:
            text = NAMES[group] + " · " + label
        strips = [{"t": text, "w": chosen["w"], "i": "trophy", "award": group}]
        break
    return {"strips": strips, "strip": strips[0] if strips else {"t": "", "w": False, "i": ""},
            "awardText": "   ·   ".join(lines), "awardOtherText": "   ·   ".join(lines),
            "awardRowText": "", "aw": [], "ay": 0, "won": bool(strips and strips[0]["w"])}
