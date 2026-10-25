"""Calendário do WorldTour masculino (ProCyclingStats) e onde assistir cada prova.

O calendário, as etapas e os horários de largada vêm do ProCyclingStats; onde assistir vem
de uma tabela mantida à mão (cycling_tv.json), porque nenhuma fonte aberta diz o que passa
no Brasil e o que dá para ver de fora com VPN.
"""
import datetime as dt
import html
import json
import os
import re
import threading
import time
from zoneinfo import ZoneInfo

import requests

from .common import BASE, DATA_DIR, load_json, log, save_json

PCS = "https://www.procyclingstats.com/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
CYCLING_PATH = os.path.join(DATA_DIR, "cycling.json")
TV_PATH = os.path.join(BASE, "cycling_tv.json")
BRT = ZoneInfo("America/Sao_Paulo")

COUNTRIES = {"au": "Austrália", "ae": "Emirados Árabes", "be": "Bélgica", "it": "Itália", "fr": "França",
             "es": "Espanha", "nl": "Holanda", "ch": "Suíça", "de": "Alemanha", "dk": "Dinamarca",
             "pl": "Polônia", "ca": "Canadá", "cn": "China", "gb": "Reino Unido", "us": "Estados Unidos",
             "si": "Eslovênia", "no": "Noruega", "pt": "Portugal", "at": "Áustria", "ie": "Irlanda"}
# fuso de cada prova (onde o fuso do país não basta) e de cada país
RACE_TZ = {"tour-down-under": "Australia/Adelaide", "great-ocean-road-race": "Australia/Melbourne"}
CC_TZ = {"au": "Australia/Sydney", "ae": "Asia/Dubai", "ca": "America/Toronto", "cn": "Asia/Shanghai",
         "gb": "Europe/London", "ie": "Europe/Dublin", "pt": "Europe/Lisbon", "us": "America/New_York"}
GRAND_TOURS = {"giro-d-italia", "tour-de-france", "vuelta-a-espana"}
MONUMENTS = {"milano-sanremo", "ronde-van-vlaanderen", "paris-roubaix", "liege-bastogne-liege", "il-lombardia"}
PROFILES = {"p1": "Plana", "p2": "Ondulada", "p3": "Ondulada, chegada em subida",
            "p4": "Montanha", "p5": "Montanha, chegada no alto"}
WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
DETAIL_DAYS = 60          # etapas detalhadas (largada, km, percurso) das provas que começam até lá
REFRESH = 6 * 3600

_lock = threading.Lock()
_session = requests.Session()
_session.headers["User-Agent"] = UA


def _get(path):
    """Uma página do PCS, com pausa entre pedidos para não sobrecarregar o site."""
    for attempt in range(3):
        try:
            r = _session.get(PCS + path, timeout=25)
            time.sleep(1.2)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return ""
        except requests.RequestException:
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("ProCyclingStats não respondeu: " + path)


def _text(fragment):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse_calendar(page, year):
    """Linhas da tabela de provas UWT: datas, país, slug, nome e classe."""
    races = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        m = re.search(r'<span class="flag (\w+)"></span>\s*<a\s+href="race/([a-z0-9-]+)-%d-\w+">([^<]+)</a>' % year, tr)
        k = re.search(r"<td>(\d\.UWT)</td>", tr)
        d = re.search(r'<td class="cu500"\s*>([\d. -]+)</td>', tr)
        if not (m and k and d):
            continue
        parts = [p.strip() for p in d.group(1).split("-")]
        def iso(p):
            day, month = p.split(".")
            return f"{year}-{month}-{day}"
        races.append({"slug": m.group(2), "year": year, "cc": m.group(1), "name": html.unescape(m.group(3)).strip(),
                      "class": k.group(1), "start": iso(parts[0]), "end": iso(parts[-1])})
    return races


def parse_stages(page, year):
    """Tabela de etapas de uma volta: data, perfil, nome, partida e chegada."""
    stages = []
    body = page[page.find("<tbody"):page.find("</tbody>")]
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        link = re.search(r'href="race/([a-z0-9-]+-%d-(?:stage-[\w-]+|prologue))"' % year, tr)
        if len(tds) < 3 or not link:
            continue
        month_day = _text(tds[0])
        if not re.fullmatch(r"\d\d/\d\d", month_day):
            continue
        prof = re.search(r"profile (p\d)", tr)
        name, _, route = _text(tds[2]).partition("|")
        a, _, b = route.partition(" - ")
        a, b = (x if x.strip() not in ("-", "") else "" for x in (a, b))
        stages.append({"path": link.group(1), "date": f"{year}-{month_day[:2]}-{month_day[3:]}",
                       "name": name.strip(), "from": a.strip(), "to": b.strip(),
                       "profile": prof.group(1) if prof and prof.group(1) != "p0" else ""})
    return stages


def parse_info(page):
    """Bloco de informações de uma etapa ou clássica: largada, distância, percurso."""
    out = {}
    for label, key in (("Start time", "time"), ("Distance", "km"), ("Departure", "from"), ("Arrival", "to"),
                       ("Vertical meters", "climb")):
        # cada campo: <div class="bold ...">Rótulo: </div><div ...>valor</div>...<br />
        m = re.search(r">\s*" + re.escape(label) + r":?\s*</div>(.*?)<br", page, re.S)
        if m:
            value = _text(m.group(1))
            if value and value != "-":
                out[key] = value
    m = re.search(r"Parcours type:.{0,300}?profile (p\d)", page, re.S)
    if m and m.group(1) != "p0":
        out["profile"] = m.group(1)
    if "time" in out:
        t = re.match(r"(\d{1,2}):(\d\d)", out["time"])
        out["time"] = f"{int(t.group(1)):02d}:{t.group(2)}" if t else ""
        if out["time"] == "00:00":          # o PCS usa 00:00 quando a largada ainda não saiu
            out["time"] = ""
        if not out["time"]:
            out.pop("time")
    if "km" in out:
        km = re.match(r"[\d.]+", out["km"])
        out["km"] = float(km.group(0)) if km and float(km.group(0)) > 0 else None
        if out["km"] is None:
            out.pop("km")
    return out


def _tz(race):
    return ZoneInfo(RACE_TZ.get(race["slug"]) or CC_TZ.get(race["cc"]) or "Europe/Paris")


def _to_brt(race, date, local_time):
    """Horário de largada no fuso de Brasília (data e hora)."""
    h, m = map(int, local_time.split(":"))
    y, mo, d = map(int, date.split("-"))
    when = dt.datetime(y, mo, d, h, m, tzinfo=_tz(race)).astimezone(BRT)
    return when.strftime("%Y-%m-%d"), when.strftime("%H:%M")


def refresh(force=False):
    """Relê o calendário do ano atual e do próximo e os detalhes das provas que estão perto."""
    if not _lock.acquire(blocking=False):
        return
    try:
        data = load_json(CYCLING_PATH, {}) or {}
        if not force and time.time() - (data.get("updated") or 0) < REFRESH:
            return
        old = {(r["slug"], r["year"]): r for r in data.get("races", [])}
        today = dt.date.today()
        races = []
        for year in (today.year, today.year + 1):
            try:
                races += parse_calendar(_get(f"races.php?year={year}&circuit=1&filter=Filter"), year)
            except RuntimeError:
                log.exception("ciclismo: calendário %s", year)
                races += [r for r in old.values() if r["year"] == year]
        horizon = (today + dt.timedelta(days=DETAIL_DAYS)).isoformat()
        for race in races:
            prev = old.get((race["slug"], race["year"])) or {}
            race["stages"] = prev.get("stages") or []
            if race["end"] < (today - dt.timedelta(days=3)).isoformat():
                continue                       # já acabou: fica o que se sabia
            detail = race["start"] <= horizon
            try:
                if race["class"].startswith("2."):
                    stages = parse_stages(_get(f"race/{race['slug']}/{race['year']}/stages"), race["year"])
                    known = {s["path"]: s for s in race["stages"]}
                    for s in stages:
                        s.update({k: v for k, v in (known.get(s["path"]) or {}).items() if k in ("time", "km", "climb")})
                        if detail:
                            info = parse_info(_get("race/" + s["path"].replace(f"-{race['year']}-", f"/{race['year']}/")))
                            s.update({k: v for k, v in info.items() if k not in ("from", "to") or not s.get(k)})
                    race["stages"] = stages or race["stages"]
                elif detail or not race["stages"]:
                    info = parse_info(_get(f"race/{race['slug']}/{race['year']}"))
                    race["stages"] = [{"path": "", "date": race["start"], "name": "Prova única",
                                       "from": info.get("from", ""), "to": info.get("to", ""),
                                       **{k: v for k, v in info.items() if k in ("time", "km", "climb", "profile")}}]
            except RuntimeError:
                log.exception("ciclismo: %s %s", race["slug"], race["year"])
        save_json(CYCLING_PATH, {"updated": time.time(), "races": races})
        log.info("ciclismo: %d provas atualizadas", len(races))
    finally:
        _lock.release()


def cycling_worker():
    while True:
        try:
            refresh()
        except Exception:  # noqa: BLE001 — tenta de novo na próxima volta
            log.exception("ciclismo: falha ao atualizar")
        time.sleep(1800)


def _kind(race):
    if race["slug"] in GRAND_TOURS:
        return "Grande Volta"
    if race["slug"] in MONUMENTS:
        return "Monumento"
    return "Volta" if race["class"].startswith("2.") else "Clássica"


def _short(iso):
    y, m, d = iso.split("-")
    return f"{d}/{m}"


def _stage_view(race, s):
    out = {"name": s["name"].replace("Stage", "Etapa").replace("Prologue", "Prólogo"),
           "date": s["date"], "from": s.get("from", ""), "to": s.get("to", ""),
           "km": s.get("km"), "profile": PROFILES.get(s.get("profile", ""), ""),
           "tt": bool(re.search(r"\b(ITT|TTT)\b", s["name"]))}
    if "(ITT)" in s["name"]:
        out["name"] = out["name"].replace("(ITT)", "(contrarrelógio)")
    if "(TTT)" in s["name"]:
        out["name"] = out["name"].replace("(TTT)", "(contrarrelógio por equipes)")
    day = s["date"]
    if s.get("time") and s["time"] != "00:00":
        day, out["timeBr"] = _to_brt(race, s["date"], s["time"])
        out["timeLocal"] = s["time"]
    y, m, d = map(int, day.split("-"))
    out["day"] = f"{WEEKDAYS[dt.date(y, m, d).weekday()]} {d:02d}/{m:02d}"
    # linha pronta para a lista de etapas do canal
    parts = [out["day"], out["name"]]
    if out["from"] or out["to"]:
        parts.append(out["from"] + (" → " + out["to"] if out["to"] and out["to"] != out["from"] else ""))
    if out["km"]:
        parts.append(f'{out["km"]:g} km')
    if out["profile"]:
        parts.append(out["profile"])
    if out.get("timeBr"):
        parts.append(out["timeBr"] + " (Brasília)")
    out["line"] = "  ·  ".join(parts)
    return out


# apps do Roku que dá para abrir direto da ficha (ids conferidos no Roku da sala)
ROKU_APPS = {"disney+": ("Disney+", "291097"), "espn": ("Disney+", "291097"), "hbo max": ("HBO Max", "61322"),
             "max": ("HBO Max", "61322"), "youtube": ("YouTube", "837"), "prime video": ("Prime Video", "13"),
             "paramount": ("Paramount+", "229863"), "globoplay": ("Globoplay", "564736"),
             "apple tv": ("Apple TV", "551012"), "netflix": ("Netflix", "12")}
LANGS = {"en": "inglês", "fr": "francês"}


def _app_for(service):
    low = service.lower()
    for key, app in ROKU_APPS.items():
        if key in low:
            return app
    return None


def _watch_texts(watch):
    br, abroad = watch.get("br") or [], watch.get("abroad") or []
    br_lines = [o["service"] + (f' — {o["note"]}' if o.get("note") else "") for o in br] or ["Sem transmissão conhecida no Brasil."]
    vpn_lines = []
    for o in abroad:
        where = COUNTRIES.get((o.get("country") or "").lower(), (o.get("country") or "").upper())
        bits = [o["service"], where, LANGS.get(o.get("lang"), o.get("lang") or ""), "grátis" if o.get("free") else "pago"]
        vpn_lines.append(" · ".join(b for b in bits if b) + (f' — {o["note"]}' if o.get("note") else ""))
    if not vpn_lines:
        vpn_lines = ["Nenhuma opção em inglês ou francês encontrada."]
    free = [o for o in abroad if o.get("free")]
    first = (free or abroad or [None])[0]
    vpn_short = "VPN: sem opção" if not first else         f'VPN: {first["service"]} ({(first.get("country") or "").upper()}{", grátis" if first.get("free") else ""})' +         (f" +{len(abroad) - 1}" if len(abroad) > 1 else "")
    br_short = "Brasil: " + (", ".join(o["service"] for o in br) if br else "sem transmissão")
    apps, seen = [], set()
    for o in br:
        app = _app_for(o["service"])
        if app and app[1] not in seen:
            seen.add(app[1])
            apps.append({"label": app[0], "id": app[1]})
    return {"brLines": br_lines, "vpnLines": vpn_lines, "brShort": br_short, "vpnShort": vpn_short, "apps": apps}


def cycling_feed():
    """Provas de hoje em diante (e as que terminaram há 3 dias), com onde assistir."""
    data = load_json(CYCLING_PATH, {}) or {}
    tv = (load_json(TV_PATH, {}) or {}).get("races", {})
    today = dt.date.today().isoformat()
    since = (dt.date.today() - dt.timedelta(days=3)).isoformat()
    races = []
    for r in sorted(data.get("races", []), key=lambda r: r["start"]):
        if r["end"] < since:
            continue
        watch = tv.get(r["slug"]) or {}
        status = "live" if r["start"] <= today <= r["end"] else "done" if r["end"] < today else "next"
        races.append({
            "id": f'{r["slug"]}-{r["year"]}', "name": r["name"], "kind": _kind(r),
            "cc": r["cc"], "country": COUNTRIES.get(r["cc"], r["cc"].upper()),
            "start": r["start"], "end": r["end"], "year": r["year"],
            "dates": _short(r["start"]) if r["start"] == r["end"] else f'{_short(r["start"])} – {_short(r["end"])}',
            "status": status, "br": watch.get("br") or [], "abroad": watch.get("abroad") or [],
            "stages": [_stage_view(r, s) for s in r.get("stages") or []],
            **_watch_texts(watch),
        })
        st = races[-1]["stages"]
        races[-1]["stagesNote"] = ("Horários de largada ainda não divulgados." if st and not any(x.get("timeBr") for x in st)
                                   else "Horários de largada no fuso de Brasília." if st else "Etapas ainda não divulgadas.")
    updated = data.get("updated") or 0
    text = "Atualizado em " + time.strftime("%d/%m às %H:%M", time.localtime(updated)) if updated else ""
    return {"races": races, "updated": updated, "updatedText": text, "today": today}
