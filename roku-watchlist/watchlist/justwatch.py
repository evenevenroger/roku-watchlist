"""JustWatch: em quais serviços cada título está no Brasil, com o link para o Roku."""
import re
import time
import unicodedata

import requests

from .common import CONFIG


JW_URL = "https://apis.justwatch.com/graphql"
JW_HEADERS = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
Q_JW = """query($q:String!){ popularTitles(country:BR, first:5, filter:{searchQuery:$q}){
  edges{ node{ id objectType content(country:BR, language:"pt"){ title originalTitle originalReleaseYear fullPath externalIds{imdbId} }
  offers(country:BR, platform:WEB){ monetizationType standardWebURL deeplinkURL(platform:ROKU_OS)
  package{ clearName technicalName } } } } } }"""


class JustWatchUnavailable(RuntimeError):
    pass


def norm(s):
    """Título comparável: sem acentos, minúsculo, só letras e números."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def same_title(node, item):
    """Reserva quando o JustWatch não liga o filme ao IMDb: mesmo título e ano (±1)."""
    c = node.get("content") or {}
    other_id = (c.get("externalIds") or {}).get("imdbId")
    if other_id and other_id != item["id"]:
        return False
    if not item.get("year") or not c.get("originalReleaseYear"):
        return False
    if abs(c["originalReleaseYear"] - item["year"]) > 1:
        return False
    mine = {norm(item.get("original")), norm(item.get("title"))} - {""}
    return bool(mine & {norm(c.get("originalTitle")), norm(c.get("title"))})


def jw_lookup(item):
    """Procura o título no JustWatch e devolve as ofertas no Brasil."""
    queries = []
    for q in (item.get("original"), item.get("title")):
        if q and q not in queries:
            queries.append(q)
    for q in queries:
        edges, r = None, None
        for attempt in range(3):
            try:
                time.sleep(1.5)          # devagar: o JustWatch bloqueia rajadas
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
        nodes = [e["node"] for e in edges]
        match = next((n for n in nodes if ((n.get("content") or {}).get("externalIds") or {}).get("imdbId") == item["id"]), None)
        match = match or next((n for n in nodes if same_title(n, item)), None)
        if match:
            return {"found": True, "jw_path": match["content"].get("fullPath"),
                    "offers": simplify_offers(match.get("offers") or [])}
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
