"""Dados enxutos para o canal do Roku e o pacote .zip do canal."""
import io
import os
import zipfile

import time

from .awards import AWARD_NAMES, AWARDS
from .common import CHANNEL_DIR, CONFIG, lan_ip
from .data import build_payload


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


NEW_DAYS = 21


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
    # sinopse, elenco e como tocar vão uma vez por título (não repetem em cada lista)
    details = {}
    for r in rows:
        for it in r["items"]:
            d = {k: it.pop(k) for k in ("plot", "cast", "play", "awardText", "country") if k in it}
            for k in ("genres", "directors", "sortTitle", "awardRowText"):   # o canal monta a partir das listas
                it.pop(k, None)
            if d:
                details[it["id"]] = d
    return {"rows": rows, "details": details, "status": status_info(p),
            "server": f"http://{lan_ip()}:{CONFIG.get('port', 8765)}"}


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
