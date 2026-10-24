"""Sincronização (IMDb → JustWatch) e montagem dos dados para a página e o canal."""
import time
import threading

from .awards import AWARDS, fetch_awards
from .common import CACHE_PATH, CONFIG, RT_PATH, load_json, lock, log, save_json, state
from .imdb import fetch_english_titles, fetch_list, fetch_rated, fetch_titles, fetch_user_lists
from .justwatch import JustWatchUnavailable, jw_lookup, roku_link, service_for
from .rottentomatoes import rt_lock
from .tv_awards import read_cache as read_tv_awards, sync_tv_awards
from .series_runtime import PATH as SERIES_RUNTIME_PATH, sync_series_runtimes


# ---------- sincronização ----------

def start_sync(force_offers=False):
    """Reserva a execução antes de responder ao celular, inclusive quando ela é rápida."""
    with lock:
        if state["running"]:
            return False
        state.update(running=True, error=None, outcome="running", started_at=time.time(),
                     completed_at=None, problems=[], done=0, total=0, step="Iniciando")
    threading.Thread(target=sync, args=(force_offers, True), daemon=True).start()
    return True


def sync_status():
    cache = load_json(CACHE_PATH, {})
    persisted = cache_status(cache)
    with lock:
        current = dict(state)
    # Depois de reiniciar o processo, o resultado persistido prevalece sobre o estado vazio.
    if not current.get("running"):
        current.update(outcome=persisted["outcome"], problems=persisted["problems"])
        current["error"] = (cache.get("last_error") or {}).get("msg") if persisted["problems"] else None
    elif current.get("total") and (cache.get("sync_result") or {}).get("started_at") == current.get("started_at"):
        # O contador ao vivo inclui consultas feitas desde o último checkpoint em disco.
        coverage = dict(persisted["coverage"])
        outside_queue = max(0, coverage["pending"] - len(cache.get("offers_queue") or []))
        pending = min(coverage["total"], max(0, current["total"] - current.get("done", 0)) + outside_queue)
        coverage.update(pending=pending, fresh=coverage["total"] - pending)
        persisted.update(coverage=coverage, pending_offers=pending)
    return {**current, **{k: v for k, v in persisted.items() if k not in ("outcome", "problems")},
            "synced_at": cache.get("synced_at"),
            "synced_label": time.strftime("%d/%m %H:%M", time.localtime(cache["synced_at"])) if cache.get("synced_at") else "sem consulta confirmada",
            "full_synced_at": cache.get("full_synced_at")}


def availability_summary(cache, now=None):
    """Cobertura atual das listas ativas, incluindo uma eventual fila de atualização forçada."""
    now = time.time() if now is None else now
    ids = {tid for values in cache.get("lists", {}).values() for tid in values}
    offers = cache.get("offers", {})
    max_age = CONFIG.get("offers_max_age_days", 3) * 86400
    pending = {tid for tid in ids if now - offers.get(tid, {}).get("ts", 0) >= max_age}
    pending.update(set(cache.get("offers_queue") or []) & ids)
    missing = sum(not offers.get(tid, {}).get("ts") for tid in ids)
    return {"total": len(ids), "fresh": len(ids) - len(pending), "pending": len(pending), "missing": missing,
            "max_age_days": max_age / 86400}


def cache_status(cache, now=None):
    coverage = availability_summary(cache, now)
    result = dict(cache.get("sync_result") or {})
    # As versões antigas registravam o limite de um lote como falha parcial.
    problems = [p for p in result.get("problems", []) if not p.startswith("Faltam consultar ")]
    outcome = result.get("outcome", "idle")
    if outcome != "failed":
        if problems:
            outcome = "partial"
        elif coverage["pending"]:
            outcome = "pending"
        elif outcome in ("partial", "pending", "running"):
            outcome = "success"
    result.update(outcome=outcome, problems=problems, pending_offers=coverage["pending"])
    return {"outcome": outcome, "problems": problems, "last_result": result,
            "coverage": coverage, "pending_offers": coverage["pending"],
            "incomplete": bool(coverage["pending"] or problems or outcome == "failed")}


def sync_action(cache, now=None):
    """Retoma uma fila normal já; falhas de fonte mantêm o intervalo de duas horas."""
    now = time.time() if now is None else now
    status = cache_status(cache, now)
    attempted = (cache.get("sync_result") or {}).get("finished_at") or cache.get("sync_attempt_at") or 0
    if status["problems"] or status["outcome"] == "failed":
        return "full" if now - attempted >= 7200 else None
    metadata_at = cache.get("metadata_synced_at", cache.get("synced_at")) or 0
    if now - metadata_at >= 86400:
        return "full"
    if status["pending_offers"]:
        return "offers"
    return None


def sync(force_offers=False, reserved=False, offers_only=False):
    with lock:
        if state["running"] and not reserved:
            return
        state.update(running=True, error=None, done=0, total=0, step="Lendo listas do IMDb",
                     outcome="running", started_at=time.time(), completed_at=None, problems=[])
    problems = []
    data_saved = False
    try:
        cache = load_json(CACHE_PATH, {"titles": {}, "lists": {}, "offers": {}})
        cache.setdefault("metadata_synced_at", cache.get("synced_at") or 0)
        if offers_only:
            lists = cache.get("lists", {})
            problems = cache_status(cache)["problems"]
            data_saved = bool(lists)
        else:
            lists = {}
            state["step"] = "Lendo as suas notas no IMDb"
            rated_all = fetch_rated(1)
            cache["my_ratings"] = {t["id"]: v for t, v in rated_all}
            if CONFIG.get("auto_lists", True):
                try:
                    cache["user_lists"] = fetch_user_lists()
                except Exception:  # noqa: BLE001 — segue com as listas já conhecidas
                    log.exception("não consegui ler as suas listas públicas")
                    problems.append("Não foi possível descobrir novas listas do IMDb.")
            all_lists = effective_lists(cache)
            for i, L in enumerate(all_lists):
                state["step"] = f"Lendo lista {i + 1}/{len(all_lists)}: {L['name']}"
                if L["id"].startswith("award:"):
                    group = L["id"].split(":", 1)[1]
                    cats = [c for c, _ in AWARDS[group][2]]
                    fresh = (time.time() - (cache.get("awards_at") or {}).get(group, 0) < AWARDS_MAX_AGE
                             and (cache.get("awards_cats") or {}).get(group) == cats)   # categorias mudaram: relê
                    if fresh and L["id"] in (cache.get("lists") or {}) and group in (cache.get("awards") or {}):
                        # prêmios mudam uma vez por ano: reaproveita o que já foi lido neste mês
                        lists[L["id"]] = cache["lists"][L["id"]]
                        continue
                    try:
                        awards = fetch_awards(group)
                        state["step"] = f"Buscando {len(awards)} filmes do {L['name']} no IMDb"
                        items = fetch_titles(awards)
                    except Exception:  # noqa: BLE001 — fica a cópia anterior; relê na próxima
                        log.exception("não consegui reler %s; mantenho a cópia anterior", L["name"])
                        problems.append("Lista preservada sem atualizar: " + L["name"])
                        if L["id"] in (cache.get("lists") or {}):
                            lists[L["id"]] = cache["lists"][L["id"]]
                        continue
                    cache.setdefault("awards", {})[group] = awards
                    cache.setdefault("awards_at", {})[group] = time.time()
                    cache.setdefault("awards_cats", {})[group] = cats
                    newest = {tid: max((a["y"] or 0) for a in v) for tid, v in awards.items()}
                    items.sort(key=lambda t: (-newest.get(t["id"], 0), t["title"] or ""))
                elif L["id"].startswith("rated"):
                    minimum = int(L["id"][5:] or 8)
                    items = [t for t, v in rated_all if v >= minimum]
                else:
                    try:
                        items = fetch_list(L["id"])
                    except Exception:  # noqa: BLE001 — ex.: lista que virou privada; fica a cópia anterior
                        log.exception("não consegui ler a lista %s; mantenho a cópia anterior", L["name"])
                        problems.append("Lista preservada sem atualizar: " + L["name"])
                        if L["id"] in (cache.get("lists") or {}):
                            lists[L["id"]] = cache["lists"][L["id"]]
                        continue
                lists[L["id"]] = [t["id"] for t in items]
                for t in items:
                    cache["titles"][t["id"]] = {**cache["titles"].get(t["id"], {}), **t}
            cache["lists"] = lists
            active_ids = {tid for values in lists.values() for tid in values}
            movies_missing_english = [tid for tid in active_ids
                                      if (cache.get("titles", {}).get(tid) or {}).get("type") not in ("tvSeries", "tvMiniSeries")
                                      and not (cache["titles"][tid].get("poster_en"))]
            if movies_missing_english:
                try:
                    english = fetch_english_titles(movies_missing_english)
                    for tid, values in english.items():
                        cache["titles"][tid].update({"title_en": values.get("english"),
                                                     "poster_en": values.get("poster"),
                                                     "country_ids": values.get("country_ids", []),
                                                     "language_ids": values.get("language_ids", [])})
                except Exception as exc:  # noqa: BLE001 — títulos antigos continuam aparecendo em português
                    log.exception("não consegui completar os nomes em inglês dos filmes")
            save_json(CACHE_PATH, cache)
            data_saved = True

            try:
                ids = {tid for values in lists.values() for tid in values}
                sync_tv_awards([cache["titles"][tid] for tid in ids if tid in cache["titles"]])
            except Exception as exc:
                log.exception("não consegui atualizar todos os prêmios de séries; mantenho os anteriores")
                problems.append("Prêmios de séries parcialmente atualizados: " + str(exc))

            try:
                _, result = sync_series_runtimes([cache["titles"][tid] for tid in active_ids
                                                   if tid in cache["titles"]])
                if result["failed"]:
                    log.warning("duração não confirmada para %s de %s séries", result["failed"], result["total"])
            except Exception as exc:  # noqa: BLE001 — outros dados e serviços continuam sincronizando
                log.exception("não consegui atualizar as durações totais das séries")
                problems.append("Durações de séries parcialmente atualizadas: " + str(exc))
            if not problems:
                cache["metadata_synced_at"] = time.time()

        max_age = CONFIG.get("offers_max_age_days", 3) * 86400
        all_ids = {tid for values in lists.values() for tid in values}
        queued = set(cache.get("offers_queue") or []) & all_ids
        todo = [tid for tid in all_ids if tid in queued or force_offers
                or time.time() - cache["offers"].get(tid, {}).get("ts", 0) >= max_age]
        todo.sort(key=lambda tid: (cache["offers"].get(tid, {}).get("ts", 0), tid))
        # A fila inteira continua com o ritmo limitado em jw_lookup. Checkpoints permitem
        # retomar uma interrupção sem reler listas ou repetir os títulos já consultados.
        state.update(step="Consultando onde cada título passa", total=len(todo), done=0)
        cache["sync_attempt_at"] = time.time()
        cache["offers_queue"] = todo
        cache["offers_incomplete"] = bool(todo)
        cache["sync_result"] = {"outcome": "running", "problems": problems,
                                "started_at": state["started_at"], "pending_offers": len(todo)}
        save_json(CACHE_PATH, cache)
        completed = 0
        try:
            for tid in todo:
                res = jw_lookup(cache["titles"][tid])
                res["ts"] = time.time()
                cache["offers"][tid] = res
                completed += 1
                state["done"] = completed
                if completed % 25 == 0:
                    cache["offers_queue"] = todo[completed:]
                    save_json(CACHE_PATH, cache)
        except Exception:
            # Nenhuma outra consulta é iniciada depois de um bloqueio/erro da fonte.
            cache["offers_queue"] = todo[completed:]
            cache["offers_incomplete"] = bool(cache["offers_queue"])
            track_availability(cache, all_ids)
            save_json(CACHE_PATH, cache)
            raise
        cache["offers_queue"] = []
        pending = availability_summary(cache)["pending"]
        cache["offers_incomplete"] = pending > 0
        track_availability(cache, all_ids)
        cache["synced_at"] = time.time()
        cache["last_error"] = None
        cache["sync_incomplete"] = bool(problems or pending)
        outcome = "partial" if problems else "pending" if pending else "success"
        cache["sync_result"] = {"outcome": outcome, "problems": problems,
                                "pending_offers": pending, "finished_at": time.time()}
        if not problems and not pending:
            cache["full_synced_at"] = cache["synced_at"]
        save_json(CACHE_PATH, cache)
        state.update(outcome=outcome, problems=problems)
        state["step"] = "Atualização concluída" if not pending else f"Mais {pending} títulos aguardando atualização automática"
        log.info("sincronização %s (%s títulos consultados; %s pendentes)", outcome, completed, pending)
    except Exception as e:  # noqa: BLE001 — mostrar qualquer falha na página
        state["error"] = str(e)
        log.exception("falha na sincronização")
        c = load_json(CACHE_PATH, {})
        if c:
            c["last_error"] = {"msg": str(e), "ts": time.time()}
            c["sync_incomplete"] = True
            outcome = "partial" if data_saved else "failed"
            c["sync_result"] = {"outcome": outcome, "problems": problems + [str(e)],
                                "finished_at": time.time()}
            save_json(CACHE_PATH, c)
        state.update(outcome="partial" if data_saved else "failed", problems=problems + [str(e)])
    finally:
        state.update(running=False, completed_at=time.time())


AWARDS_MAX_AGE = 30 * 86400


def effective_lists(cache):
    """Listas do config.json na ordem dele, com o nome atual do IMDb, mais as listas
    públicas novas (entram depois das suas listas e antes de Vistos/Oscar/Cannes).
    A watchlist (predefinida) não aparece como lista comum."""
    discovered = cache.get("user_lists") or []
    names = {d["id"]: d["name"] for d in discovered}
    watch_id = CONFIG.get("watchlist_list_id", "")
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
        # título consultado pela 1ª vez: não sabemos quando chegou, então não é novidade
        known = not first_time and tid in avail
        seen = avail.get(tid, {})
        avail[tid] = {s: seen.get(s, now if known else 0) for s in current}


def build_payload():
    cache = load_json(CACHE_PATH, {"titles": {}, "lists": {}, "offers": {}})
    with rt_lock:
        rt = load_json(RT_PATH, {})
    titles = []
    tv_awards = read_tv_awards().get("titles", {})
    runtimes = load_json(SERIES_RUNTIME_PATH, {})
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
                       "series_runtime": runtimes.get(tid) or {},
                       "tv_awards": tv_awards.get(tid, {}).get("entries", {}),
                       "checked": bool(o), "checked_at": o.get("ts"), "jw": o.get("jw_path"),
                       "my_rating": (cache.get("my_ratings") or {}).get(tid),
                       # chegou = quando ficou disponível pela 1ª vez em algum serviço seu
                       # (entrar em mais um serviço não é novidade)
                       "new_since": min(((cache.get("avail") or {}).get(tid) or {}).values() or [0]),
                       "rt_critics": (rt.get(tid) or {}).get("c") or None,
                       "rt_audience": (rt.get(tid) or {}).get("a") or None,
                       "awards": {g: v[tid] for g, v in (cache.get("awards") or {}).items()
                                  if tid in v}})
    lists = [{"id": L["id"], "name": L["name"], "items": cache["lists"].get(L["id"], [])}
             for L in effective_lists(cache)]
    status = cache_status(cache)
    return {"titles": titles, "lists": lists, "synced_at": cache.get("synced_at"),
            "last_error": cache.get("last_error"), "incomplete": status["incomplete"],
            "sync_result": status["last_result"], "full_synced_at": cache.get("full_synced_at"),
            "coverage": status["coverage"], "pending_offers": status["pending_offers"],
            "services": [s["name"] for s in CONFIG["services"]]}
