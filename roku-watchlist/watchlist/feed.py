"""Dados enxutos para o canal do Roku e o pacote .zip do canal."""
import hashlib
import io
import json
import os
import zipfile

import time
import unicodedata

from .awards import AWARD_ICONS, AWARD_NAMES, AWARDS
from .common import CACHE_PATH, CHANNEL_DIR, CONFIG, RECENT_PATH, RT_PATH, lan_ip, load_json, save_json
from .data import build_payload


# nomes curtos para quando várias categorias dividem a mesma tarja
SHORT_CAT = {"Melhor filme": "Filme", "Filme internacional": "Internacional", "Grande Prêmio do Júri": "Júri",
             "Prêmio do Júri": "Júri", "Prêmio Especial do Júri": "Júri especial", "Prêmio do Público": "Público",
             "Júri internacional": "Júri intern.", "Público internacional": "Público intern."}


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
    # tarjas do pôster: uma por festival em que o filme venceu (no máximo duas), na ordem de
    # AWARD_NAMES; várias categorias do mesmo festival viram um texto só, com nomes curtos
    strips = []
    for g in AWARD_NAMES:
        order = [c for c, _ in AWARDS[g][2]]
        won = sorted({a["c"] for a in aw.get(g, []) if a["w"]}, key=lambda c: order.index(c) if c in order else 99)
        if won and len(strips) < 2:
            text = won[0] if len(won) == 1 else " + ".join(SHORT_CAT.get(c, c) for c in won)
            strips.append({"t": text, "w": True, "i": AWARD_ICONS[g]})
    if not strips and aw.get("oscar"):
        strips.append({"t": "Indicado", "w": False, "i": "trophy"})
    strip = strips[0] if strips else {"t": "", "w": False, "i": ""}
    # prêmios que não são o da lista atual (vão para a faixa de informações)
    other = [ln for ln in lines if not (group and ln.startswith(AWARD_NAMES.get(group, group) + " "))]
    return {
        "strip": strip,                         # canal até o build 8
        "strips": strips,
        "awardOtherText": ("Também: " if group else "Prêmios: ") + "; ".join(other) if other else "",
        "awardRowText": row_text,
        "awardText": "   ·   ".join(lines),
        "aw": [{"c": a["c"], "y": str(a["y"] or ""), "w": bool(a["w"])} for a in mine],
        "ay": max([a["y"] or 0 for a in mine] or [0]),
        "won": any(a["w"] for a in mine),
    }


NEW_DAYS = 21
RECENT_MAX = 30


def record_play(tid):
    """Guarda o título no topo de "Vistos recentemente" (sem repetir)."""
    recent = [r for r in (load_json(RECENT_PATH, []) or []) if r.get("id") != tid]
    recent.insert(0, {"id": tid, "ts": int(time.time())})
    save_json(RECENT_PATH, recent[:RECENT_MAX])


def play_steps(m):
    """Como abrir o título sem o PC (o canal manda os comandos ao próprio Roku):
    o link e a regra de perfil do app, se houver."""
    link = m["roku"] or ""
    app_id = link.split(":", 1)[1] if link.startswith("search:") else link.split("?")[0].split("/")[-1]
    rule = (CONFIG.get("after_launch") or {}).get(app_id) or {}
    return {"l": link, "w": rule.get("wait", 0), "k": rule.get("keys", []),
            "ra": rule.get("relaunch_after", -1) if rule.get("relaunch_after") is not None else -1}


def status_info(p):
    synced = p.get("synced_at")
    err = p.get("last_error")
    return {
        "synced": time.strftime("%d/%m %H:%M", time.localtime(synced)) if synced else "",
        "error": (err or {}).get("msg", "") if err and (not synced or err["ts"] > synced) else "",
        "incomplete": p.get("incomplete", False),
    }


POSTER_PRE, POSTER_SUF = "https://m.media-amazon.com/images/M/", "._V1_QL75_UX300_.jpg"


def roku_feed(fmt=1, have=""):
    """Versão enxuta para o canal: só títulos disponíveis nos seus serviços.
    fmt 2 (canal build 8+): pôster só com o código da imagem, sem os prêmios do letreiro,
    e com "version"; se o canal já tem essa versão (have), volta só {"same": true}."""
    feed = roku_feed_full()
    feed.pop("_oscar", None)
    if fmt < 2:
        return feed
    for r in feed["rows"]:
        for it in r["items"]:
            it.pop("awardOtherText", None)
            if fmt >= 3:
                it.pop("strip", None)
            p = it.get("poster") or ""
            if p.startswith(POSTER_PRE) and p.endswith(POSTER_SUF):
                it["poster"] = p[len(POSTER_PRE):-len(POSTER_SUF)]
    version = hashlib.md5(json.dumps(feed, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    if have and have == version:
        return {"same": True, "version": version}
    feed["version"] = version
    return feed


# ---------- canal build 12+: tela inicial enxuta, uma lista por vez e busca no PC ----------

_memo = {"key": None, "feed": None}


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


def compact_feed():
    """Feed fmt 3 (sem os campos antigos), refeito só quando os dados mudam (ou a cada hora,
    por causa da janela de novidades)."""
    key = (_mtime(CACHE_PATH), _mtime(RT_PATH), _mtime(RECENT_PATH), int(time.time() // 3600))
    if _memo["key"] != key:
        feed = roku_feed_full()
        for r in feed["rows"]:
            for it in r["items"]:
                it.pop("awardOtherText", None)
                it.pop("strip", None)
                p = it.get("poster") or ""
                if p.startswith(POSTER_PRE) and p.endswith(POSTER_SUF):
                    it["poster"] = p[len(POSTER_PRE):-len(POSTER_SUF)]
        feed["_rows"] = {r["id"]: _row_payload(feed, r) for r in feed["rows"]}   # (corpo, versão)
        oscar = feed.pop("_oscar", {})
        feed["_covers"] = (_pick_covers(feed["rows"], oscar, lambda i: True),
                           _pick_covers(feed["rows"], oscar, lambda i: not i["mine"]))
        _memo.update(key=key, feed=feed)
    return _memo["feed"]


def _hash(obj):
    return hashlib.md5(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def _row_payload(feed, r):
    det = {i["id"]: feed["details"][i["id"]] for i in r["items"] if i["id"] in feed["details"]}
    body = {"row": r, "details": det}
    return body, _hash(body)


def roku_home(have=""):
    """Só os cartões: nome, quantidades, as 3 capas e a versão de cada lista."""
    feed = compact_feed()
    rows = []
    for r in feed["rows"]:
        _, v = feed["_rows"][r["id"]]
        unseen = [i for i in r["items"] if not i["mine"]]     # sem nota sua no IMDb
        rows.append({"id": r["id"], "name": r["name"], "total": r["total"], "award": r["award"],
                     "count": len(r["items"]), "v": v, "covers": feed["_covers"][0][r["id"]],
                     "unseen": len(unseen), "coversUnseen": feed["_covers"][1][r["id"]]})
    home = {"rows": rows, "status": feed["status"], "server": feed["server"]}
    version = _hash(home)
    if have and have == version:
        return {"same": True, "version": version}
    home["version"] = version
    return home


def roku_list(list_id, have=""):
    feed = compact_feed()
    if list_id not in feed["_rows"]:
        return {"error": "lista não encontrada"}
    body, v = feed["_rows"][list_id]
    if have and have == v:
        return {"same": True, "v": v}
    return {**body, "v": v}


def _fold(text):
    return "".join(c for c in unicodedata.normalize("NFD", (text or "").lower()) if unicodedata.category(c) != "Mn")


def roku_search(q):
    """Títulos de todas as listas cujo nome (em português ou original) contém q, sem ligar para acentos."""
    feed = compact_feed()
    q = _fold(q).strip()
    found = {}
    for r in feed["rows"]:
        for it in r["items"]:
            if q and (q in _fold(it["title"]) or q in _fold(it.get("orig"))):
                if it["id"] not in found or (found[it["id"]][0] and not r["award"]):
                    found[it["id"]] = (r["award"], it)
    items = []
    for _, it in found.values():
        it = dict(it)
        it["pos"] = len(items)
        items.append(it)
    det = {i["id"]: feed["details"][i["id"]] for i in items if i["id"] in feed["details"]}
    return {"items": items, "details": det}


def roku_feed_full():
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
                "orig": (t.get("original") or "").lower(),
                "newSince": int(t.get("new_since") or 0),
                "play": [play_steps(m) for m in t["mine"]],
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
                row["icon"] = AWARD_ICONS[group]
            rows.append(row)
    # novidades: o que entrou nos seus serviços nas últimas semanas, de qualquer lista
    cutoff = time.time() - NEW_DAYS * 86400
    seen, fresh = set(), []
    for r in rows:
        for it in r["items"]:
            if it["newSince"] > cutoff and it["id"] not in seen:
                seen.add(it["id"])
                fresh.append(dict(it))
    fresh.sort(key=lambda it: -it["newSince"])
    for i, it in enumerate(fresh):
        it["pos"] = i
    if fresh:
        rows.insert(0, {"id": "new", "name": "Chegou nos seus serviços", "total": len(fresh),
                        "award": False, "items": fresh})
    # vistos recentemente: o que você abriu pelo canal, do mais recente ao mais antigo
    first = {}
    for r in rows:
        for it in r["items"]:
            if it["id"] not in first or (first[it["id"]][0] and not r["award"]):
                first[it["id"]] = (r["award"], it)      # prefere a cópia de uma lista comum
    recent = []
    for rec in load_json(RECENT_PATH, []) or []:
        hit = first.get(rec.get("id"))
        if hit:
            it = dict(hit[1])
            it["pos"] = len(recent)
            recent.append(it)
    if recent:
        rows.insert(0, {"id": "recent", "name": "Vistos recentemente", "total": len(recent),
                        "award": False, "items": recent})
    # sinopse, elenco e como tocar vão uma vez por título (não repetem em cada lista)
    details = {}
    for r in rows:
        for it in r["items"]:
            d = {k: it.pop(k) for k in ("plot", "cast", "play", "awardText", "country") if k in it}
            for k in ("genres", "directors", "sortTitle", "awardRowText"):   # o canal monta a partir das listas
                it.pop(k, None)
            if d:
                details[it["id"]] = d
    # categorias do Oscar que cada título venceu (para escolher as capas dos cartões)
    oscar = {}
    for r in rows:
        for it in r["items"]:
            t = by_id.get(it["id"]) or {}
            won = {a["c"] for a in (t.get("awards") or {}).get("oscar", []) if a["w"]}
            if won:
                oscar[it["id"]] = won
    return {"rows": rows, "details": details, "status": status_info(p),
            "server": f"http://{lan_ip()}:{CONFIG.get('port', 8765)}", "_oscar": oscar}


FESTIVALS = {"award:cannes", "award:veneza", "award:berlim", "award:sundance"}


def _cover_tiers(r):
    """Ordem de preferência das capas de um cartão: categorias do Oscar vencidas, a cada uma
    pelas maiores notas IMDb; depois vencedores de outros festivais (tarja no pôster);
    depois, quem sobrar, também pela nota. None = mantém a ordem
    própria do cartão (novidades e vistos recentemente: os mais recentes; festivais: a nota)."""
    if r["id"] in ("new", "recent") or r["id"] in FESTIVALS:
        return None
    if r["id"] == "award:oscar":
        return ["Melhor filme"]
    if "document" in _fold(r["name"]):
        return ["Documentário"]
    if "animat" in _fold(r["name"]) or "animac" in _fold(r["name"]):
        return ["Animação", "Melhor filme", "Roteiro", "Filme internacional"]
    return ["Melhor filme", "Roteiro", "Filme internacional"]


def _pick_covers(rows, oscar, keep):
    """3 capas por cartão sem repetir filme entre cartões. O Oscar escolhe primeiro, depois as
    outras listas na ordem da tela, e por último festivais, novidades e vistos recentemente."""
    first = [r for r in rows if r["id"] == "award:oscar"]
    last = [r for r in rows if _cover_tiers(r) is None]
    order = first + [r for r in rows if r not in first and r not in last] + last
    used, out = set(), {}
    for r in order:
        items = [i for i in r["items"] if keep(i) and i.get("poster")]
        tiers = _cover_tiers(r)
        if tiers is None:
            ranked = items if r["id"] in ("new", "recent") else sorted(items, key=lambda i: -i["r"])
        else:
            by_r = sorted(items, key=lambda i: -i["r"])
            festival = [i for i in by_r if any(s["w"] and s["i"] != "trophy" for s in i.get("strips") or [])]
            ranked = [i for c in tiers for i in by_r if c in oscar.get(i["id"], ())] + festival + by_r
        picked, ids = [], set()
        for i in ranked:
            if i["id"] in used or i["id"] in ids:
                continue
            picked.append(i)
            ids.add(i["id"])
            if len(picked) == 3:
                break
        if len(picked) < 3:      # lista pequena: completa mesmo repetindo capa de outro cartão
            picked += [i for i in ranked if i["id"] not in ids][:3 - len(picked)]
        used |= ids
        out[r["id"]] = [i["poster"] for i in picked[:3]]
    return out


def build_channel_zip(host):
    """Empacota o canal com o endereço deste servidor embutido."""
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
