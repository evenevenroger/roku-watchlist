"""Watchlist → Roku.

Lê as listas do IMDb, descobre onde cada título está nos seus streamings
(dados do JustWatch, Brasil) e manda o Roku abrir o título no app certo.

Uso:  python app.py           (abre em http://localhost:8765)
"""
import json
import re
import os
import socket
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.json")
CACHE_PATH = os.path.join(BASE, "data", "cache.json")
STATIC = os.path.join(BASE, "static")

IMDB_URL = "https://caching.graphql.imdb.com/"
IMDB_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130 Safari/537.36",
    "Origin": "https://www.imdb.com",
    "Referer": "https://www.imdb.com/",
    "x-imdb-user-country": "BR",
    "x-imdb-user-language": "pt-BR",
}
JW_URL = "https://apis.justwatch.com/graphql"
JW_HEADERS = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}

TITLE_FIELDS = """... on Title { id titleText{text} originalTitleText{text}
  releaseYear{year} titleType{id text} ratingsSummary{aggregateRating voteCount}
  primaryImage{url} runtime{seconds} titleGenres{genres{genre{text}}}
  plot{plotText{plainText}} spokenLanguages{spokenLanguages{id text}}
  countriesOfOrigin{countries{id text}}
  directors: credits(first:2, filter:{categories:["director"]}){ edges{ node{ name{ nameText{text} } } } }
  cast: credits(first:4, filter:{categories:["actor","actress"]}){ edges{ node{ name{ nameText{text} } } } } }"""
Q_TITLES = """query($ids:[ID!]!){ titles(ids:$ids){ %s } }""" % TITLE_FIELDS
Q_RATED = """query($after:String){ advancedTitleSearch(first:250, after:$after,
  constraints:{singleUserRatingConstraint:{filterType:INCLUDE, userId:"%s", ratingRange:{min:%d, max:%d}}},
  sort:{sortBy:SINGLE_USER_RATING_DATE, sortOrder:DESC}){
  total pageInfo{hasNextPage endCursor} edges{ node{ title{ %s } } } } }"""

LANGS_PT = {
    "en": "Inglês", "pt": "Português", "es": "Espanhol", "fr": "Francês", "it": "Italiano",
    "de": "Alemão", "ja": "Japonês", "ko": "Coreano", "zh": "Chinês", "cmn": "Mandarim",
    "yue": "Cantonês", "ru": "Russo", "sv": "Sueco", "da": "Dinamarquês", "no": "Norueguês",
    "nb": "Norueguês", "fi": "Finlandês", "nl": "Holandês", "pl": "Polonês", "hu": "Húngaro",
    "cs": "Tcheco", "tr": "Turco", "fa": "Persa", "ar": "Árabe", "he": "Hebraico",
    "hi": "Hindi", "ta": "Tâmil", "te": "Telugo", "th": "Tailandês", "el": "Grego",
    "ro": "Romeno", "is": "Islandês", "uk": "Ucraniano", "id": "Indonésio", "vi": "Vietnamita",
    "ga": "Irlandês", "la": "Latim", "sr": "Sérvio", "hr": "Croata", "bg": "Búlgaro",
    "ka": "Georgiano", "et": "Estoniano", "lt": "Lituano", "lv": "Letão", "tl": "Tagalo",
    "zxx": "Sem diálogos", "qbn": "Linguagem de sinais",
}
GENRES_PT = {
    "Action": "Ação", "Adventure": "Aventura", "Animation": "Animação", "Biography": "Biografia",
    "Comedy": "Comédia", "Crime": "Crime", "Documentary": "Documentário", "Drama": "Drama",
    "Family": "Família", "Fantasy": "Fantasia", "Film-Noir": "Noir", "History": "História",
    "Horror": "Terror", "Music": "Música", "Musical": "Musical", "Mystery": "Mistério",
    "Romance": "Romance", "Sci-Fi": "Ficção científica", "Sport": "Esporte",
    "Thriller": "Suspense", "War": "Guerra", "Western": "Faroeste", "Short": "Curta",
    "Reality-TV": "Reality", "Talk-Show": "Talk show", "Game-Show": "Game show", "News": "Notícias",
}
Q_WATCHLIST = """query($user:ID!,$after:String){ predefinedList(classType:WATCH_LIST, userId:$user){
  titleListItemSearch(first:250, after:$after){ total pageInfo{hasNextPage endCursor}
  edges{ title{ %s } } } } }""" % TITLE_FIELDS
Q_LIST = """query($id:ID!,$after:String){ list(id:$id){
  titleListItemSearch(first:250, after:$after){ total pageInfo{hasNextPage endCursor}
  edges{ title{ %s } } } } }""" % TITLE_FIELDS
Q_JW = """query($q:String!){ popularTitles(country:BR, first:5, filter:{searchQuery:$q}){
  edges{ node{ id objectType content(country:BR, language:"pt"){ title fullPath externalIds{imdbId} }
  offers(country:BR, platform:WEB){ monetizationType standardWebURL deeplinkURL(platform:ROKU_OS)
  package{ clearName technicalName } } } } } }"""

lock = threading.Lock()
state = {"running": False, "step": "", "done": 0, "total": 0, "error": None}


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


CONFIG = load_json(CONFIG_PATH, {})


# ---------- IMDb ----------

def imdb_query(query, variables):
    for attempt in range(3):
        r = requests.post(IMDB_URL, json={"query": query, "variables": variables},
                          headers=IMDB_HEADERS, timeout=40)
        if r.ok:
            d = r.json()
            if d.get("data"):
                return d["data"]
            raise RuntimeError(f"IMDb: {d.get('errors')}")
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"IMDb respondeu {r.status_code}")


def poster(url, width=300):
    if not url:
        return None
    return url.replace("._V1_.", f"._V1_QL75_UX{width}_.")


def parse_title(t):
    genres = [GENRES_PT.get(g["genre"]["text"], g["genre"]["text"])
              for g in ((t.get("titleGenres") or {}).get("genres") or [])]
    langs = (t.get("spokenLanguages") or {}).get("spokenLanguages") or []
    lang = langs[0] if langs else {}
    countries = (t.get("countriesOfOrigin") or {}).get("countries") or []
    directors = [e["node"]["name"]["nameText"]["text"]
                 for e in ((t.get("directors") or {}).get("edges") or [])]
    cast = [e["node"]["name"]["nameText"]["text"]
            for e in ((t.get("cast") or {}).get("edges") or [])]
    return {
        "lang": LANGS_PT.get(lang.get("id"), lang.get("text")) if lang else None,
        "country": countries[0]["text"] if countries else None,
        "directors": directors,
        "cast": cast,
        "id": t["id"],
        "title": (t.get("titleText") or {}).get("text"),
        "original": (t.get("originalTitleText") or {}).get("text"),
        "year": (t.get("releaseYear") or {}).get("year"),
        "type": (t.get("titleType") or {}).get("id"),
        "rating": (t.get("ratingsSummary") or {}).get("aggregateRating"),
        "votes": (t.get("ratingsSummary") or {}).get("voteCount"),
        "poster": poster((t.get("primaryImage") or {}).get("url")),
        "runtime": ((t.get("runtime") or {}).get("seconds") or 0) // 60 or None,
        "genres": genres,
        "plot": ((t.get("plot") or {}).get("plotText") or {}).get("plainText"),
    }


def fetch_rated(min_rating=8):
    """Títulos que você avaliou com nota >= min_rating, com a sua nota."""
    out = []
    for value in range(10, min_rating - 1, -1):
        after = None
        while True:
            d = imdb_query(Q_RATED % (CONFIG["imdb_user"], value, value, TITLE_FIELDS),
                           {"after": after})
            s = d["advancedTitleSearch"]
            for e in s["edges"]:
                t = (e.get("node") or {}).get("title")
                if t:
                    out.append((parse_title(t), value))
            if not s["pageInfo"]["hasNextPage"]:
                break
            after = s["pageInfo"]["endCursor"]
    return out


# ---------- prêmios (IMDb) ----------

AWARDS = {
    # evento IMDb, só vencedores?, regras: (categoria, função que reconhece o prêmio)
    "oscar": ("ev0000003", False, [
        ("Melhor filme", lambda t, c, y=0: t == "Oscar" and bool(re.match(
            r"(Best (Motion )?Picture|Outstanding (Motion )?Picture|Outstanding Production)", c))),
        ("Roteiro", lambda t, c, y=0: t == "Oscar" and bool(re.search(r"Screenplay|Writing", c))),
        ("Filme internacional", lambda t, c, y=0: t == "Oscar" and bool(
            re.search(r"International Feature|Foreign Language", c))),
        ("Animação", lambda t, c, y=0: t == "Oscar" and "Animated Feature" in c),
        ("Documentário", lambda t, c, y=0: t == "Oscar" and "Documentary" in c and "Short" not in c),
    ]),
    # "Grand Prize of the Festival" foi o prêmio máximo em 1946–54 e 1964–74 (= Palma);
    # nos outros anos o IMDb usa o mesmo nome para o Grand Prix, o segundo prêmio.
    "cannes": ("ev0000147", True, [
        ("Palma de Ouro", lambda t, c, y=0: t == "Palme d'Or" or (
            t == "Grand Prize of the Festival" and c in ("", "Feature Film") and festival_top(y))),
        ("Grand Prix", lambda t, c, y=0: t == "Grand Prize of the Jury" or (
            t == "Grand Prize of the Festival" and c in ("", "Feature Film") and not festival_top(y))),
        ("Prêmio do Júri", lambda t, c, y=0: t == "Jury Prize" and c == ""),
        ("Un Certain Regard", lambda t, c, y=0: t == "Un Certain Regard Award"),
    ]),
}
def festival_top(year):
    return bool(year) and (year <= 1954 or 1964 <= year <= 1974)


Q_AWARD_SEARCH = """query($after:String){ advancedTitleSearch(first:250, after:$after,
  constraints:{awardConstraint:{allEventNominations:[{eventId:"%s"%s}]}}){
  pageInfo{hasNextPage endCursor} edges{ node{ title{ id } } } } }"""
Q_AWARD_NOMS = """query($ids:[ID!]!){ titles(ids:$ids){ id
  awardNominations(first:60, filter:{events:["%s"]}){ edges{ node{ isWinner
  award{ text year category{ text } } } } } } }"""


def fetch_awards(group):
    """{imdb_id: [{"c": categoria, "y": ano, "w": venceu}]} a partir dos prêmios do IMDb."""
    event, winners_only, rules = AWARDS[group]
    ids, after = [], None
    q = Q_AWARD_SEARCH % (event, ", winnerFilter:WINNER_ONLY" if winners_only else "")
    while True:
        s = imdb_query(q, {"after": after})["advancedTitleSearch"]
        ids += [e["node"]["title"]["id"] for e in s["edges"]]
        if not s["pageInfo"]["hasNextPage"]:
            break
        after = s["pageInfo"]["endCursor"]
    out = {}
    for i in range(0, len(ids), 100):
        state["step"] = f"Lendo prêmios ({i}/{len(ids)})"
        for t in imdb_query(Q_AWARD_NOMS % event, {"ids": ids[i:i + 100]})["titles"]:
            if not t:
                continue
            found = {}
            for e in (t.get("awardNominations") or {}).get("edges") or []:
                n = e["node"]
                if winners_only and not n["isWinner"]:
                    continue
                a = n["award"] or {}
                text, cat = a.get("text") or "", (a.get("category") or {}).get("text") or ""
                for name, match in rules:
                    if match(text, cat, a.get("year") or 0):
                        prev = found.get(name)
                        if prev:
                            prev["w"] = prev["w"] or bool(n["isWinner"])
                        else:
                            found[name] = {"c": name, "y": a.get("year"), "w": bool(n["isWinner"])}
            if found:
                out[t["id"]] = list(found.values())
    return out


def fetch_titles(ids):
    """Busca títulos no IMDb pelo código, em lotes."""
    out = []
    ids = list(ids)
    for i in range(0, len(ids), 100):
        d = imdb_query(Q_TITLES, {"ids": ids[i:i + 100]})
        out += [parse_title(t) for t in d["titles"] if t]
    return out


def fetch_list(list_id):
    items, after = [], None
    while True:
        if list_id == "watchlist":
            d = imdb_query(Q_WATCHLIST, {"user": CONFIG["imdb_user"], "after": after})
            s = d["predefinedList"]["titleListItemSearch"]
        else:
            d = imdb_query(Q_LIST, {"id": list_id, "after": after})
            s = d["list"]["titleListItemSearch"]
        items += [parse_title(e["title"]) for e in s["edges"] if e.get("title")]
        if not s["pageInfo"]["hasNextPage"]:
            return items
        after = s["pageInfo"]["endCursor"]


# ---------- JustWatch ----------

class JustWatchUnavailable(RuntimeError):
    pass


def jw_lookup(item):
    """Procura o título no JustWatch e devolve as ofertas no Brasil."""
    queries = []
    for q in (item.get("original"), item.get("title")):
        if q and q not in queries:
            queries.append(q)
    for q in queries:
        edges = None
        for attempt in range(3):
            try:
                time.sleep(0.4)          # devagar: o JustWatch bloqueia rajadas
                r = requests.post(JW_URL, json={"query": Q_JW, "variables": {"q": q}},
                                  headers=JW_HEADERS, timeout=30)
                if r.status_code == 200:
                    edges = ((r.json().get("data") or {}).get("popularTitles") or {}).get("edges") or []
                    break
            except (requests.RequestException, ValueError):
                pass
            time.sleep(5 * (attempt + 1))
        if edges is None:
            # Bloqueio ou falha: não grava "não encontrado" (isso esconderia o título por dias).
            raise JustWatchUnavailable(f"JustWatch indisponível (HTTP {getattr(r, 'status_code', '?')})")
        for e in edges:
            n = e["node"]
            if ((n.get("content") or {}).get("externalIds") or {}).get("imdbId") == item["id"]:
                return {"found": True, "jw_path": n["content"].get("fullPath"),
                        "offers": simplify_offers(n.get("offers") or [])}
    return {"found": False, "offers": []}


def simplify_offers(offers):
    out, seen = [], set()
    for o in offers:
        p = o.get("package") or {}
        key = (p.get("technicalName"), o.get("monetizationType"))
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "tech": p.get("technicalName"),
            "name": p.get("clearName"),
            "kind": o.get("monetizationType"),
            "roku": o.get("deeplinkURL"),
            "web": o.get("standardWebURL"),
        })
    return out


# Código do app no Roku brasileiro quando o JustWatch traz outro (ex.: Paramount+ dos EUA).
ROKU_APP_REMAP = {"31440": "229863"}


def roku_link(service, roku, web, kind):
    """Link de ECP para abrir o título; monta um quando o JustWatch não fornece."""
    if roku and roku.startswith("launch/13"):
        # O Prime reinicia na escolha de perfil e descarta o link; a busca do
        # Roku não conhece os canais (Universal+, Filmelier) e oferece aluguel.
        # Então só abre o app e escolhe o perfil — o título é buscado lá dentro.
        return "launch/13"
    if roku:
        app_id = roku.split("?")[0].split("/")[1]
        if app_id in ROKU_APP_REMAP:
            roku = roku.replace(f"launch/{app_id}", f"launch/{ROKU_APP_REMAP[app_id]}", 1)
        return roku
    media = "series" if kind in ("tvSeries", "tvMiniSeries") else "movie"
    web = web or ""
    if service == "Disney+" and "/entity-" in web:
        uid = web.split("/entity-")[1].split("?")[0].split("/")[0]
        return f"launch/291097?contentId={uid}&mediaType={media}"
    if service == "HBO Max":
        # O Max no Roku só aceita o código do vídeo (que exige login); o JustWatch
        # traz o da página. Então vamos pela busca do Roku (ver roku_ui_search).
        return "search:61322"
    return None


def service_for(tech):
    for s in CONFIG["services"]:
        for m in s["match"]:
            if (m.startswith("*") and m[1:] in tech) or tech.startswith(m):
                return s["name"]
    return None


# ---------- sincronização ----------

def sync(force_offers=False):
    with lock:
        if state["running"]:
            return
        state.update(running=True, error=None, done=0, total=0, step="Lendo listas do IMDb")
    try:
        cache = load_json(CACHE_PATH, {"titles": {}, "lists": {}, "offers": {}})
        lists = {}
        state["step"] = "Lendo as suas notas no IMDb"
        rated_all = fetch_rated(1)
        cache["my_ratings"] = {t["id"]: v for t, v in rated_all}
        for i, L in enumerate(CONFIG["lists"]):
            state["step"] = f"Lendo lista {i + 1}/{len(CONFIG['lists'])}: {L['name']}"
            if L["id"].startswith("award:"):
                group = L["id"].split(":", 1)[1]
                awards = fetch_awards(group)
                state["step"] = f"Buscando {len(awards)} filmes do {L['name']} no IMDb"
                items = fetch_titles(awards)
                cache.setdefault("awards", {})[group] = awards
                newest = {tid: max((a["y"] or 0) for a in v) for tid, v in awards.items()}
                items.sort(key=lambda t: (-newest.get(t["id"], 0), t["title"] or ""))
            elif L["id"].startswith("rated"):
                minimum = int(L["id"][5:] or 8)
                items = [t for t, v in rated_all if v >= minimum]
            else:
                items = fetch_list(L["id"])
            lists[L["id"]] = [t["id"] for t in items]
            for t in items:
                cache["titles"][t["id"]] = t
        cache["lists"] = lists
        save_json(CACHE_PATH, cache)

        max_age = CONFIG.get("offers_max_age_days", 3) * 86400
        all_ids = {tid for ids in lists.values() for tid in ids}
        todo = [tid for tid in all_ids
                if force_offers or time.time() - cache["offers"].get(tid, {}).get("ts", 0) > max_age]
        state.update(step="Consultando onde cada título passa", total=len(todo), done=0)

        def work(tid):
            res = jw_lookup(cache["titles"][tid])
            res["ts"] = time.time()
            return tid, res

        cache["sync_attempt_at"] = time.time()
        try:
            with ThreadPoolExecutor(max_workers=3) as ex:
                for n, (tid, res) in enumerate(ex.map(work, todo), 1):
                    cache["offers"][tid] = res
                    state["done"] = n
                    if n % 100 == 0:
                        save_json(CACHE_PATH, cache)
        except JustWatchUnavailable as e:
            cache["offers_incomplete"] = True
            save_json(CACHE_PATH, cache)
            raise RuntimeError(f"{e}. Guardei o que já tinha; tento de novo em 2 horas.")
        cache["offers_incomplete"] = False
        cache["synced_at"] = time.time()
        save_json(CACHE_PATH, cache)
        state["step"] = "Pronto"
    except Exception as e:  # noqa: BLE001 — mostrar qualquer falha na página
        state["error"] = str(e)
    finally:
        state["running"] = False


# ---------- Rotten Tomatoes ----------
# O endereço do RT de cada filme vem do Wikidata (P1258, ligado ao IMDb por P345);
# as duas notas vêm da página pública do filme. Fica num arquivo próprio (rt.json)
# e é atualizado devagar, em segundo plano, a cada 30 dias por título.

RT_PATH = os.path.join(BASE, "data", "rt.json")
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
        if path:
            try:
                entry.update(rt_scores(path))
            except requests.RequestException:
                time.sleep(60)          # RT recusou: tenta numa próxima rodada
                continue
            time.sleep(1.5)
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
            pass
        time.sleep(1800)


def build_payload():
    cache = load_json(CACHE_PATH, {"titles": {}, "lists": {}, "offers": {}})
    with rt_lock:
        rt = load_json(RT_PATH, {})
    titles = []
    for tid, t in cache["titles"].items():
        o = cache["offers"].get(tid) or {}
        mine, others, rent = [], [], False
        for off in o.get("offers", []):
            if off["kind"] in ("RENT", "BUY"):
                rent = True
                continue
            svc = service_for(off["tech"] or "")
            link = roku_link(svc, off["roku"], off["web"], t.get("type"))
            entry = {"service": svc or off["name"], "web": off["web"], "roku": link,
                     "direct": bool(link and ("contentI" in link or link.startswith("search:")))}
            if svc:
                if all(m["service"] != svc for m in mine):
                    mine.append(entry)
            elif all(x["service"] != entry["service"] for x in others):
                others.append(entry)
        titles.append({**t, "mine": mine, "others": others, "rent": rent,
                       "checked": bool(o), "jw": o.get("jw_path"),
                       "my_rating": (cache.get("my_ratings") or {}).get(tid),
                       "rt_critics": (rt.get(tid) or {}).get("c") or None,
                       "rt_audience": (rt.get(tid) or {}).get("a") or None,
                       "awards": {g: v[tid] for g, v in (cache.get("awards") or {}).items()
                                  if tid in v}})
    lists = [{"id": L["id"], "name": L["name"], "items": cache["lists"].get(L["id"], [])}
             for L in CONFIG["lists"]]
    return {"titles": titles, "lists": lists, "synced_at": cache.get("synced_at"),
            "services": [s["name"] for s in CONFIG["services"]]}


# ---------- Roku ----------

def discover_roku():
    """Procura um Roku na rede (SSDP)."""
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
           'MAN: "ssdp:discover"\r\nMX: 2\r\nST: roku:ecp\r\n\r\n').encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3)
    try:
        s.sendto(msg, ("239.255.255.250", 1900))
        while True:
            data, addr = s.recvfrom(2048)
            if b"roku" in data.lower():
                return addr[0]
    except OSError:
        return None
    finally:
        s.close()


def roku_ip(refresh=False):
    ip = CONFIG.get("roku_ip")
    if refresh or not ip:
        found = discover_roku()
        if found and found != ip:
            CONFIG["roku_ip"] = found
            save_json(CONFIG_PATH, CONFIG)
            ip = found
    return ip


def roku_post(path):
    """POST para o ECP do Roku; tenta redescobrir o IP se ele mudou."""
    last = None
    for refresh in (False, True):
        ip = roku_ip(refresh)
        if not ip:
            continue
        try:
            r = requests.post(f"http://{ip}:8060/{path}", timeout=6)
            if r.status_code == 403:
                return False, ("O Roku recusou o comando. No Roku: Configurações › Sistema › "
                               "Configurações avançadas do sistema › Controle por apps móveis › "
                               "Acesso à rede › Permissivo.")
            if r.ok:
                return True, None
            last = f"Roku respondeu {r.status_code}"
        except requests.RequestException as e:
            last = f"Roku não respondeu ({e.__class__.__name__})"
    return False, last or "Roku não encontrado na rede"


KEYS = {"Home", "Back", "Select", "Up", "Down", "Left", "Right", "Play", "Rev", "Fwd",
        "InstantReplay", "Info", "VolumeUp", "VolumeDown", "VolumeMute", "PowerOff", "PowerOn"}


def roku_active_app():
    try:
        r = requests.get(f"http://{roku_ip()}:8060/query/active-app", timeout=4)
        return r.text
    except requests.RequestException:
        return ""


def play_with_profile(link, rule):
    """Para apps que abrem na escolha de perfil e perdem o link (Disney+):
    se o app já está aberto, manda o link direto; senão abre, escolhe o perfil
    e manda o link de novo."""
    app_id = link.split("?")[0].split("/")[1]
    if "?" in link and f'id="{app_id}"' in roku_active_app():
        return roku_post(link)
    ok, err = roku_post(link)
    if not ok:
        return ok, err

    def run():
        time.sleep(rule.get("wait", 12))
        for k in rule.get("keys", []):
            if k in KEYS:
                roku_post(f"keypress/{k}")
                time.sleep(0.7)
        if rule.get("relaunch_after") is not None and "?" in link:
            time.sleep(rule["relaunch_after"])
            roku_post(link)

    threading.Thread(target=run, daemon=True).start()
    return True, None


busy = threading.Lock()


def roku_ui_search(title, app_id):
    """Imita o controle: Pesquisar no menu do Roku, digita o título, abre o 1º
    resultado e aperta o 1º "Assistir agora"; depois escolhe o perfil do app.
    (O comando de busca do ECP não acha nada no catálogo brasileiro; a busca
    digitada na tela acha.)"""
    if not busy.acquire(blocking=False):
        return False, "Já estou abrindo outro título no Roku, aguarde."

    def key(k, wait=0.45):
        roku_post(f"keypress/{k}")
        time.sleep(wait)

    def run():
        try:
            key("Home", 4)
            for _ in range(5):          # Tela inicial → Pesquisar
                key("Down", 0.5)
            key("Select", 3.5)
            for ch in title.lower():
                key("Lit_" + urllib.parse.quote(ch, safe=""), 0.25)
            time.sleep(3)
            for _ in range(6):          # do "a" do teclado até o 1º resultado
                key("Right")
            time.sleep(1)
            key("Select", 4)            # página do título
            key("Select", 0.5)          # 1º "Assistir agora"
            rule = (CONFIG.get("after_launch") or {}).get(app_id)
            if rule:
                time.sleep(rule.get("wait", 14))
                for k in rule.get("keys", []):
                    key(k, 0.7)
        finally:
            busy.release()

    threading.Thread(target=run, daemon=True).start()
    return True, None


def roku_search(title, year, kind):
    q = {"keyword": title, "type": "series" if kind in ("tvSeries", "tvMiniSeries") else "movie",
         "launch": "true"}
    return roku_post("search/browse?" + urllib.parse.urlencode(q))


def play_link(link, title, title_pt=None, kind=None, year=None):
    if link.startswith("search:"):
        return roku_ui_search(title_pt or title, link.split(":", 1)[1])
    if link.startswith("launch/"):
        rule = (CONFIG.get("after_launch") or {}).get(link.split("?")[0].split("/")[1])
        return play_with_profile(link, rule) if rule else roku_post(link)
    return roku_search(title, year, kind)


# ---------- canal do Roku ----------

CHANNEL_DIR = os.path.join(BASE, "roku-channel")


AWARD_NAMES = {"oscar": "Oscar", "cannes": "Cannes"}


def award_fields(t, list_id):
    """Prêmios do título. Nas listas de prêmio, só os daquele prêmio (para filtrar);
    o texto da ficha sempre mostra todos."""
    aw = t.get("awards") or {}
    lines = []
    for g, entries in aw.items():
        by_year = {}
        for a in entries:
            by_year.setdefault(a["y"] or 0, []).append(
                a["c"] + (" (venceu)" if a["w"] else " (indicado)" if g == "oscar" else ""))
        for y in sorted(by_year, reverse=True):
            lines.append(f'{AWARD_NAMES.get(g, g)} {y or ""}: ' + ", ".join(by_year[y]))
    group = list_id.split(":", 1)[1] if list_id.startswith("award:") else None
    mine = aw.get(group) or []
    row_text = ""
    if mine:
        by_year = {}
        for a in mine:
            by_year.setdefault(a["y"] or 0, []).append(
                a["c"] + (" (venceu)" if a["w"] else " (indicado)" if group == "oscar" else ""))
        row_text = "   ·   ".join(f'{AWARD_NAMES.get(group, group)} {y or ""}: ' + ", ".join(v)
                                   for y, v in sorted(by_year.items(), reverse=True))
    # faixa do pé do pôster nas listas comuns: o prêmio mais importante do filme
    strip = {"t": "", "w": False, "i": ""}
    for g in ("oscar", "cannes"):
        won = [a for a in aw.get(g, []) if a["w"]]
        if won:
            strip = {"t": won[0]["c"], "w": True, "i": "palm" if g == "cannes" else "trophy"}
            break
    else:
        if aw.get("oscar"):
            strip = {"t": "Indicado", "w": False, "i": "trophy"}
    # prêmios que não são o da lista atual (vão para a faixa de informações)
    other = [ln for ln in lines if not (group and ln.startswith(AWARD_NAMES.get(group, group) + " "))]
    return {
        "strip": strip,
        "awardOtherText": ("Também: " if group else "Prêmios: ") + "; ".join(other) if other else "",
        "awardRowText": row_text,
        "awardText": "   ·   ".join(lines),
        "aw": [{"c": a["c"], "y": str(a["y"] or ""), "w": bool(a["w"])} for a in mine],
        "ay": max([a["y"] or 0 for a in mine] or [0]),
        "won": any(a["w"] for a in mine),
    }


def roku_feed():
    """Versão enxuta para o canal: só títulos disponíveis nos seus serviços."""
    p = build_payload()
    by_id = {t["id"]: t for t in p["titles"]}
    rows = []
    for L in p["lists"]:
        items = []
        for tid in L["items"]:
            t = by_id.get(tid)
            if not t or not t["mine"]:
                continue
            items.append({
                "id": t["id"], "title": t["title"] or "", "year": str(t["year"] or ""),
                "y": t["year"] or 0, "pos": len(items),
                "rating": f'{t["rating"]:.1f}' if t["rating"] else "",
                "r": float(t["rating"] or 0),
                "mine": t.get("my_rating") or 0,
                "rtC": t.get("rt_critics") or "", "rtA": t.get("rt_audience") or "",
                "runtime": t["runtime"] or 0, "rtSort": t["runtime"] or 9999,
                "genres": ", ".join(t["genres"] or []), "genreList": t["genres"] or [],
                "lang": t.get("lang") or "Desconhecido",
                "country": t.get("country") or "",
                "directors": ", ".join(t.get("directors") or []),
                "directorList": t.get("directors") or [],
                "cast": ", ".join(t.get("cast") or []),
                **award_fields(t, L["id"]),
                "series": t.get("type") in ("tvSeries", "tvMiniSeries"),
                "plot": t["plot"] or "", "poster": t["poster"] or "",
                "sortTitle": (t["title"] or "").lower(),
                "services": [m["service"] for m in t["mine"]],
                "direct": [bool(m["direct"]) for m in t["mine"]],
            })
        if items:
            row = {"id": L["id"], "name": L["name"].strip(), "total": len(L["items"]),
                   "award": L["id"].startswith("award:"), "items": items}
            if row["award"]:
                # quantos indicados/premiados existem por ano e categoria (inclusive fora dos serviços)
                group = L["id"].split(":", 1)[1]
                totals = {}
                for tid in L["items"]:
                    for a in ((by_id.get(tid) or {}).get("awards") or {}).get(group, []):
                        k = f'{a["y"]}|{a["c"]}'
                        totals[k] = totals.get(k, 0) + 1
                row["totals"] = totals
                row["cats"] = [c for c, _ in AWARDS[group][2]]
            rows.append(row)
    return {"rows": rows}


def build_channel_zip(host):
    """Empacota o canal com o endereço deste servidor embutido."""
    import io
    import zipfile
    server = f"http://{lan_ip()}:{CONFIG.get('port', 8765)}"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(CHANNEL_DIR):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, CHANNEL_DIR).replace(os.sep, "/")
                data = open(full, "rb").read()
                if rel.endswith(".brs"):
                    data = data.replace(b"__SERVER__", server.encode())
                z.writestr(rel, data)
    return buf.getvalue()


# ---------- servidor ----------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            with open(os.path.join(STATIC, "index.html"), "rb") as f:
                return self.send(200, f.read(), "text/html; charset=utf-8")
        if path == "/api/data":
            return self.send(200, build_payload())
        if path == "/api/status":
            return self.send(200, state)
        if path == "/api/roku":
            return self.send(200, roku_feed())
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
            return self.send(200, {"ok": ok, "error": err})
        if path == "/api/key":
            k = self.body().get("key")
            if k not in KEYS:
                return self.send(400, {"ok": False, "error": "tecla inválida"})
            ok, err = roku_post(f"keypress/{k}")
            return self.send(200, {"ok": ok, "error": err})
        self.send(404, {"error": "não encontrado"})


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    import sys
    if sys.stdout:   # com pythonw (início automático, sem janela) não há saída
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    port = int(os.environ.get("PORT") or CONFIG.get("port", 8765))
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

    threading.Thread(target=auto_sync, daemon=True).start()
    threading.Thread(target=rt_worker, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Watchlist → Roku rodando:\n  neste PC:  http://localhost:{port}\n"
          f"  no celular (mesmo Wi-Fi):  http://{lan_ip()}:{port}\nCtrl+C para parar.")
    srv.serve_forever()
