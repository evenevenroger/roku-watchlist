"""IMDb: listas, watchlist, suas notas e dados dos títulos (API GraphQL do site)."""
import time

import requests

from .common import CONFIG


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

TITLE_FIELDS = """... on Title { id titleText{text} originalTitleText{text}
  releaseYear{year} titleType{id text} ratingsSummary{aggregateRating voteCount}
  primaryImage{url} runtime{seconds} titleGenres{genres{genre{text}}}
  plot{plotText{plainText}} spokenLanguages{spokenLanguages{id text}}
  countriesOfOrigin{countries{id text}}
  directors: credits(first:2, filter:{categories:["director"]}){ edges{ node{ name{ nameText{text} } } } }
  cast: credits(first:4, filter:{categories:["actor","actress"]}){ edges{ node{ name{ nameText{text} } } } } }"""
Q_TITLES = """query($ids:[ID!]!){ titles(ids:$ids){ %s } }""" % TITLE_FIELDS
Q_ENGLISH = """query($ids:[ID!]!){ titles(ids:$ids){ id titleText{text} primaryImage{url}
  countriesOfOrigin{countries{id}} spokenLanguages{spokenLanguages{id}} } }"""
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


# ---------- IMDb ----------

def imdb_query(query, variables):
    problem = "sem resposta"
    for attempt in range(3):
        try:
            r = requests.post(IMDB_URL, json={"query": query, "variables": variables},
                              headers=IMDB_HEADERS, timeout=40)
        except requests.RequestException as e:      # queda de conexão: tenta de novo
            problem = f"sem conexão ({e.__class__.__name__})"
        else:
            if r.ok:
                d = r.json()
                if d.get("data"):
                    return d["data"]
                raise RuntimeError(f"IMDb: {d.get('errors')}")
            problem = f"respondeu {r.status_code}"
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"IMDb {problem}")


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


def fetch_titles(ids):
    """Busca títulos no IMDb pelo código, em lotes."""
    out = []
    ids = list(ids)
    for i in range(0, len(ids), 100):
        d = imdb_query(Q_TITLES, {"ids": ids[i:i + 100]})
        out += [parse_title(t) for t in d["titles"] if t]
    return out


def fetch_english_titles(ids):
    """Retorna o título IMDb em inglês e os países/idiomas para identificar obras lusófonas."""
    headers = {**IMDB_HEADERS, "x-imdb-user-country": "US", "x-imdb-user-language": "en-US"}
    out = {}
    ids = list(dict.fromkeys(ids))
    for i in range(0, len(ids), 100):
        d = imdb_query_with_headers(Q_ENGLISH, {"ids": ids[i:i + 100]}, headers)
        for t in d.get("titles") or []:
            if not t:
                continue
            out[t["id"]] = {
                "english": (t.get("titleText") or {}).get("text"),
                "poster": poster((t.get("primaryImage") or {}).get("url")),
                "country_ids": [c.get("id") for c in ((t.get("countriesOfOrigin") or {}).get("countries") or []) if c.get("id")],
                "language_ids": [l.get("id") for l in ((t.get("spokenLanguages") or {}).get("spokenLanguages") or []) if l.get("id")],
            }
    return out


def imdb_query_with_headers(query, variables, headers):
    """Mesma chamada/repetições da IMDb, com idioma de apresentação específico."""
    problem = "sem resposta"
    for attempt in range(3):
        try:
            r = requests.post(IMDB_URL, json={"query": query, "variables": variables},
                              headers=headers, timeout=40)
        except requests.RequestException as e:
            problem = f"sem conexão ({e.__class__.__name__})"
        else:
            if r.ok:
                d = r.json()
                if d.get("data"):
                    return d["data"]
                raise RuntimeError(f"IMDb: {d.get('errors')}")
            problem = f"respondeu {r.status_code}"
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"IMDb {problem}")


Q_USER_LISTS = """query($user:ID!){ userListSearch(first:100, listOwnerUserId:$user){
  edges{ node{ id name{originalText} listType{id} visibility{id} } } } }"""


def fetch_user_lists():
    """Suas listas públicas de títulos no IMDb (a watchlist vem à parte)."""
    d = imdb_query(Q_USER_LISTS, {"user": CONFIG["imdb_user"]})
    out = []
    for e in d["userListSearch"]["edges"]:
        n = e["node"]
        if (n.get("listType") or {}).get("id") == "TITLES" and (n.get("visibility") or {}).get("id") == "PUBLIC":
            out.append({"id": n["id"], "name": (n.get("name") or {}).get("originalText") or n["id"]})
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
            seen = set()                    # o IMDb deixa pôr o mesmo título duas vezes numa lista
            return [t for t in items if not (t["id"] in seen or seen.add(t["id"]))]
        after = s["pageInfo"]["endCursor"]
