"""Sincronização (IMDb → JustWatch) e montagem dos dados para a página e o canal."""
import time
from concurrent.futures import ThreadPoolExecutor

from .awards import fetch_awards
from .common import CACHE_PATH, CONFIG, RT_PATH, load_json, lock, log, save_json, state
from .imdb import fetch_list, fetch_rated, fetch_titles, fetch_user_lists
from .justwatch import JustWatchUnavailable, jw_lookup, roku_link, service_for
from .rottentomatoes import rt_lock


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
        if CONFIG.get("auto_lists", True):
            try:
                cache["user_lists"] = fetch_user_lists()
            except Exception:  # noqa: BLE001 — segue com as listas já conhecidas
                log.exception("não consegui ler as suas listas públicas")
        all_lists = effective_lists(cache)
        for i, L in enumerate(all_lists):
            state["step"] = f"Lendo lista {i + 1}/{len(all_lists)}: {L['name']}"
            if L["id"].startswith("award:"):
                group = L["id"].split(":", 1)[1]
                fresh = time.time() - (cache.get("awards_at") or {}).get(group, 0) < AWARDS_MAX_AGE
                if fresh and L["id"] in (cache.get("lists") or {}) and group in (cache.get("awards") or {}):
                    # prêmios mudam uma vez por ano: reaproveita o que já foi lido neste mês
                    lists[L["id"]] = cache["lists"][L["id"]]
                    continue
                awards = fetch_awards(group)
                state["step"] = f"Buscando {len(awards)} filmes do {L['name']} no IMDb"
                items = fetch_titles(awards)
                cache.setdefault("awards", {})[group] = awards
                cache.setdefault("awards_at", {})[group] = time.time()
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
        # nunca consultados primeiro; no máximo N por rodada (o resto fica para daqui a 2 h)
        todo.sort(key=lambda t: cache["offers"].get(t, {}).get("ts", 0))
        per_run = CONFIG.get("jw_per_run", 500)
        pending = len(todo) - per_run
        todo = todo[:per_run]
        state.update(step="Consultando onde cada título passa", total=len(todo), done=0)

        def work(tid):
            res = jw_lookup(cache["titles"][tid])
            res["ts"] = time.time()
            return tid, res

        cache["sync_attempt_at"] = time.time()
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                for n, (tid, res) in enumerate(ex.map(work, todo), 1):
                    cache["offers"][tid] = res
                    state["done"] = n
                    if n % 100 == 0:
                        save_json(CACHE_PATH, cache)
        except JustWatchUnavailable as e:
            cache["offers_incomplete"] = True
            track_availability(cache, all_ids)
            save_json(CACHE_PATH, cache)
            raise RuntimeError(f"{e}. Guardei o que já tinha; tento de novo em 2 horas.")
        cache["offers_incomplete"] = pending > 0
        track_availability(cache, all_ids)
        cache["synced_at"] = time.time()
        cache["last_error"] = None
        save_json(CACHE_PATH, cache)
        state["step"] = "Pronto" if pending <= 0 else f"Pronto por agora; faltam {pending} títulos (próxima rodada em 2 h)"
        log.info("sincronização ok (%s títulos pendentes)", max(pending, 0))
    except Exception as e:  # noqa: BLE001 — mostrar qualquer falha na página
        state["error"] = str(e)
        log.exception("falha na sincronização")
        c = load_json(CACHE_PATH, {})
        if c:
            c["last_error"] = {"msg": str(e), "ts": time.time()}
            save_json(CACHE_PATH, c)
    finally:
        state["running"] = False


AWARDS_MAX_AGE = 30 * 86400


def effective_lists(cache):
    """Listas do config.json na ordem dele, com o nome atual do IMDb, mais as listas
    públicas novas (entram depois das suas listas e antes de Vistos/Oscar/Cannes).
    A watchlist (predefinida) não aparece como lista comum."""
    discovered = cache.get("user_lists") or []
    names = {d["id"]: d["name"] for d in discovered}
    watch_id = CONFIG.get("watchlist_list_id", "ls001832334")
    configured = [dict(L, name=names.get(L["id"], L["name"])) for L in CONFIG["lists"]]
    known = {L["id"] for L in configured} | {watch_id}
    new = [{"id": d["id"], "name": d["name"]} for d in discovered if d["id"] not in known]
    special = ("rated", "award:")
    head = [L for L in configured if not L["id"].startswith(special)]
    tail = [L for L in configured if L["id"].startswith(special)]
    return head + new + tail


def track_availability(cache, ids):
    """Quando cada título apareceu em cada serviço seu (para a fileira de novidades).
    Na primeira vez, tudo conta como antigo (0); depois, guarda a data em que surgiu."""
    first_time = "avail" not in cache
    avail = cache.setdefault("avail", {})
    now = time.time()
    for tid in ids:
        o = cache["offers"].get(tid)
        if not o:
            continue
        current = {service_for(off["tech"] or "") for off in o.get("offers", [])
                   if off["kind"] not in ("RENT", "BUY")} - {None}
        seen = avail.get(tid, {})
        avail[tid] = {s: seen.get(s, 0 if first_time else now) for s in current}


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
                       "new_since": max(((cache.get("avail") or {}).get(tid) or {}).values() or [0]),
                       "rt_critics": (rt.get(tid) or {}).get("c") or None,
                       "rt_audience": (rt.get(tid) or {}).get("a") or None,
                       "awards": {g: v[tid] for g, v in (cache.get("awards") or {}).items()
                                  if tid in v}})
    lists = [{"id": L["id"], "name": L["name"], "items": cache["lists"].get(L["id"], [])}
             for L in effective_lists(cache)]
    return {"titles": titles, "lists": lists, "synced_at": cache.get("synced_at"),
            "last_error": cache.get("last_error"), "incomplete": bool(cache.get("offers_incomplete")),
            "services": [s["name"] for s in CONFIG["services"]]}
