"""Rotten Tomatoes: endereço do filme pelo Wikidata e as duas notas pela página pública."""
import json
import re
import threading
import time

import requests

from .common import CACHE_PATH, RT_PATH, load_json, log, save_json


# ---------- Rotten Tomatoes ----------
# O endereço do RT de cada filme vem do Wikidata (P1258, ligado ao IMDb por P345);
# as duas notas vêm da página pública do filme. Fica num arquivo próprio (rt.json)
# e é atualizado devagar, em segundo plano, a cada 30 dias por título.

RT_MAX_AGE = 30 * 86400
RT_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130 Safari/537.36", "Accept-Language": "en-US,en;q=0.9"}
rt_lock = threading.Lock()


WD_URL = "https://query.wikidata.org/sparql"
WD_HEADERS = {"User-Agent": "roku-watchlist/1.0 (uso pessoal)",
              "Accept": "application/sparql-results+json"}


def wikidata(query):
    for attempt in range(4):
        try:
            r = requests.get(WD_URL, params={"query": query}, headers=WD_HEADERS, timeout=120)
            if r.ok:
                return r.json()["results"]["bindings"]
        except (requests.RequestException, ValueError):
            pass
        time.sleep(5 * (attempt + 1))
    raise RuntimeError("Wikidata não respondeu")


def rt_resolve_paths(ids):
    """{imdb_id: "m/slug"} pelo Wikidata, em lotes."""
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 200):
        values = " ".join(f'"{x}"' for x in ids[i:i + 200])
        q = f"SELECT ?imdb ?rt WHERE {{ VALUES ?imdb {{ {values} }} ?f wdt:P345 ?imdb ; wdt:P1258 ?rt . }}"
        for b in wikidata(q):
            out.setdefault(b["imdb"]["value"], b["rt"]["value"])
        time.sleep(1)
    return out


def rt_scores(path):
    r = requests.get("https://www.rottentomatoes.com/" + path, headers=RT_HEADERS, timeout=30)
    if r.status_code == 404:
        return {}
    r.raise_for_status()
    m = re.search(r'id="media-scorecard-json"[^>]*>\s*(\{.*?\})\s*</script>', r.text, re.S)
    if not m:
        return {}
    d = json.loads(m.group(1))
    return {"c": (d.get("criticsScore") or {}).get("score") or "",
            "a": (d.get("audienceScore") or {}).get("score") or ""}


def rt_search(item):
    """Procura no RT pelo título e só aceita o resultado que tem alguém do elenco do IMDb."""
    cast = {c.lower() for c in item.get("cast") or []}
    if not cast:
        return None
    for q in dict.fromkeys(filter(None, [item.get("original"), item.get("title")])):
        r = requests.get("https://www.rottentomatoes.com/search", params={"search": q},
                         headers=RT_HEADERS, timeout=30)
        if not r.ok:
            return None
        for attrs, inner in re.findall(r"<search-page-media-row([^>]*)>(.*?)</search-page-media-row>", r.text, re.S):
            row_cast = {c.strip().lower() for c in (re.search(r'cast="([^"]*)"', attrs) or [None, ""])[1].split(",")}
            url = re.search(r'href="https://www\.rottentomatoes\.com/(m/[^"]+)"', inner)
            if url and cast & row_cast:
                return url.group(1)
        time.sleep(1.5)
    return None


def rt_update():
    cache = load_json(CACHE_PATH, {})
    wanted = {tid for ids in (cache.get("lists") or {}).values() for tid in ids}
    rt = load_json(RT_PATH, {})
    now = time.time()
    stale = [t for t in wanted if now - (rt.get(t) or {}).get("ts", 0) > RT_MAX_AGE]
    offers = cache.get("offers") or {}
    stale.sort(key=lambda t: 0 if (offers.get(t) or {}).get("found") else 1)  # disponíveis primeiro
    if not stale:
        return
    need_path = [t for t in stale if not (rt.get(t) or {}).get("path")]
    paths = rt_resolve_paths(need_path) if need_path else {}
    for n, tid in enumerate(stale, 1):
        entry = rt.get(tid) or {}
        path = entry.get("path") or paths.get(tid)
        try:
            if not path and not entry.get("searched"):
                title = (cache.get("titles") or {}).get(tid) or {}
                path = rt_search(title)
                entry["searched"] = True        # só conta como procurado se a busca respondeu
            if path:
                entry.update(rt_scores(path))
                time.sleep(1.5)
        except requests.RequestException as e:
            # RT recusou ou caiu: para esta rodada (a próxima é em 30 min) em vez de
            # insistir título por título
            log.warning("RT indisponível (%s): %s; paro esta rodada", tid, e)
            break
        entry.update(path=path, ts=now)
        rt[tid] = entry
        if n % 25 == 0:
            with rt_lock:
                save_json(RT_PATH, rt)
    with rt_lock:
        save_json(RT_PATH, rt)


def rt_worker():
    while True:
        try:
            rt_update()
        except Exception:  # noqa: BLE001 — tenta de novo na próxima rodada
            log.exception("falha ao atualizar o Rotten Tomatoes")
        time.sleep(1800)
