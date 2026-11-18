"""Atualiza listas/rotten100.json com a lista da Wikipedia de filmes com 100% no Rotten Tomatoes.

Uso (na pasta roku-watchlist):
    python tools/atualizar_rotten100.py            grava o arquivo
    python tools/atualizar_rotten100.py --teste    só mostra o que mudaria

Filmes que já estão no arquivo mantêm o código do IMDb (inclusive os corrigidos à mão).
Os novos vêm do Wikidata (pela página da Wikipedia) ou da busca do IMDb (título e ano iguais),
e são conferidos no IMDb pelo ano. O que não der para resolver fica de fora e aparece no fim,
para ser buscado à mão e acrescentado ao arquivo com o mesmo título e ano da Wikipedia.
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse

import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
from watchlist.imdb import imdb_query  # noqa: E402

PATH = os.path.join(BASE, "listas", "rotten100.json")
PAGE = "List_of_films_with_a_100%_rating_on_Rotten_Tomatoes"
SOURCE = "https://en.wikipedia.org/wiki/List_of_films_with_a_100%25_rating_on_Rotten_Tomatoes"
NAME = "Filmes com 100% no Rotten Tomatoes"
H = {"User-Agent": "MinhaWatchlist/1.0 (lista pessoal)"}
FILM_TYPES = ("movie", "tvMovie", "tvSpecial", "video", "short", "tvShort")
Q_YEARS = """query($ids:[ID!]!){ titles(ids:$ids){ id titleText{text} releaseYear{year} } }"""


def norm(s):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower())


def get_json(url, params=None):
    r = None
    for attempt in range(6):
        r = requests.get(url, headers=H, params=params, timeout=40)
        if r.ok and r.text.startswith("{"):
            return r.json()
        time.sleep(5 * (attempt + 1))          # Wikidata às vezes responde vazio quando é muita consulta
    if r is not None:
        r.raise_for_status()
    raise RuntimeError(f"resposta inválida de {url}")


def parse(wikitext):
    """[{year, title, page, rt}] na ordem da tabela (o ano vem com rowspan nas linhas seguintes)."""
    table = wikitext[wikitext.index('{| class="wikitable'):]
    table = table[:table.index("\n|}")]
    rows, year = [], None
    for chunk in table.split("\n|-")[2:]:
        cells = [l[1:].strip() for l in chunk.strip().split("\n") if l.startswith("|")]
        if not cells:
            continue
        first = re.sub(r'rowspan="?\d+"?\s*\|', "", cells[0]).strip()
        if re.fullmatch(r"\d{4}", first):
            year, cells = int(first), cells[1:]
        name, page = cells[0], None
        m = re.search(r"\{\{sortname\|([^}]*)\}\}", name)
        if m:
            parts = m.group(1).split("|")
            kw = dict(p.split("=", 1) for p in parts if "=" in p)
            title = " ".join([p for p in parts if "=" not in p][:2]).strip()
            if not kw.get("nolink"):
                page = title + (f" ({kw['dab']})" if kw.get("dab") else "")
        else:
            m = re.search(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", name)
            if m:
                page, title = m.group(1).strip(), (m.group(2) or m.group(1)).strip()
            else:
                title = re.sub(r"''+|\{\{.*?\}\}|<.*?>", "", name).strip()
        rt = re.search(r"rottentomatoes\.com/m/([^|\s}]+)", chunk)
        rows.append({"year": year, "title": title, "page": page, "rt": rt.group(1) if rt else None})
    return rows


def imdb_years(ids):
    out = {}
    for i in range(0, len(ids), 100):
        for t in imdb_query(Q_YEARS, {"ids": ids[i:i + 100]})["titles"]:
            if t:
                out[t["id"]] = (t.get("releaseYear") or {}).get("year") or 0
    return out


def from_wikidata(rows):
    """Código do IMDb pela página da Wikipedia → Wikidata (P345); com mais de um, escolhe pelo ano."""
    pages = list(dict.fromkeys(r["page"] for r in rows if r["page"]))
    qid = {}
    for i in range(0, len(pages), 50):
        q = get_json("https://en.wikipedia.org/w/api.php", {
            "action": "query", "prop": "pageprops", "ppprop": "wikibase_item", "redirects": 1,
            "format": "json", "titles": "|".join(pages[i:i + 50])})["query"]
        norm_ = {n["from"]: n["to"] for n in q.get("normalized", [])}
        redir = {n["from"]: n["to"] for n in q.get("redirects", [])}
        got = {p["title"]: p.get("pageprops", {}).get("wikibase_item") for p in q["pages"].values()}
        for p in pages[i:i + 50]:
            t = norm_.get(p, p)
            qid[p] = got.get(redir.get(t, t))
    qs = list(dict.fromkeys(v for v in qid.values() if v))
    claims = {}
    for i in range(0, len(qs), 45):
        d = get_json("https://www.wikidata.org/w/api.php", {
            "action": "wbgetentities", "ids": "|".join(qs[i:i + 45]), "props": "claims", "format": "json"})
        for q, e in d["entities"].items():
            claims[q] = [c["mainsnak"].get("datavalue", {}).get("value") for c in e.get("claims", {}).get("P345", [])]
            claims[q] = [v for v in claims[q] if v and v.startswith("tt")]
        time.sleep(1)
    many = [v for vs in claims.values() if len(vs) > 1 for v in vs]
    years = imdb_years(many) if many else {}
    out = {}
    for r in rows:
        vs = claims.get(qid.get(r["page"]), [])
        if len(vs) > 1:
            vs = [v for v in vs if abs(years.get(v, 0) - r["year"]) <= 1]
        if len(vs) == 1:
            out[id(r)] = vs[0]
    return out


def from_search(r):
    found = []
    for q in (f"{r['title']} {r['year']}", r["title"]):
        url = "https://v3.sg.media-imdb.com/suggestion/x/%s.json" % urllib.parse.quote(q)
        found += requests.get(url, headers=H, timeout=20).json().get("d", [])
        time.sleep(0.3)
    ids = list(dict.fromkeys(x["id"] for x in found if x["id"].startswith("tt") and x.get("qid") in FILM_TYPES
                             and x.get("y") and abs(x["y"] - r["year"]) <= 1 and norm(x.get("l")) == norm(r["title"])))
    return ids[0] if len(ids) == 1 else None


def main():
    dry = "--teste" in sys.argv
    text = requests.get("https://en.wikipedia.org/w/index.php", headers=H, timeout=40,
                        params={"title": PAGE, "action": "raw"}).text
    rows = parse(text)
    if len(rows) < 300:
        sys.exit(f"Só achei {len(rows)} filmes na Wikipedia; a tabela deve ter mudado de formato. Nada foi gravado.")
    with open(PATH, encoding="utf-8") as f:
        old = json.load(f)["items"]
    by_rt = {i["rt"]: i["imdb"] for i in old if i.get("rt")}
    by_title = {(norm(i["title"]), i["year"]): i["imdb"] for i in old}
    for r in rows:
        r["imdb"] = by_rt.get(r["rt"]) or by_title.get((norm(r["title"]), r["year"]))
    new = [r for r in rows if not r["imdb"]]
    if new:
        wd = from_wikidata(new)
        for r in new:
            r["imdb"] = wd.get(id(r)) or from_search(r)
        checked = [r["imdb"] for r in new if r["imdb"]]
        years = imdb_years(checked) if checked else {}
        for r in new:
            if r["imdb"] and abs(years.get(r["imdb"], 0) - r["year"]) > 1:
                r["imdb"] = None                # ano não bate: melhor buscar à mão
    seen, items, missing = set(), [], []
    for r in rows:
        if not r["imdb"]:
            missing.append(r)
        elif r["imdb"] not in seen:
            seen.add(r["imdb"])
            items.append({"pos": len(items) + 1, "title": r["title"], "year": r["year"], "imdb": r["imdb"], "rt": r["rt"]})
    old_ids = {i["imdb"] for i in old}
    added = [i for i in items if i["imdb"] not in old_ids]
    removed = [i for i in old if i["imdb"] not in seen]
    print(f"Wikipedia: {len(rows)} filmes | no arquivo: {len(items)} (antes {len(old)})")
    for i in added:
        print(f"  + {i['year']} {i['title']} ({i['imdb']})")
    for i in removed:
        print(f"  - {i['year']} {i['title']} ({i['imdb']})")
    for r in missing:
        print(f"  ? {r['year']} {r['title']} — sem código do IMDb; buscar à mão")
    if dry:
        print("Teste: nada foi gravado.")
        return
    with open(PATH, "w", encoding="utf-8") as f:
        f.write('{\n  "name": %s,\n  "source": %s,\n  "items": [\n' % (json.dumps(NAME), json.dumps(SOURCE)))
        f.write(",\n".join("    " + json.dumps(i, ensure_ascii=False) for i in items))
        f.write("\n  ]\n}\n")
    print("Gravado:", PATH)


if __name__ == "__main__":
    main()
