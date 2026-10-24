"""Duração acumulada das séries, somando a duração cadastrada de cada episódio no IMDb."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

import requests

from .common import DATA_DIR, load_json, save_json
from .imdb import IMDB_HEADERS, IMDB_URL
import os

PATH = os.path.join(DATA_DIR, "series_runtimes.json")
MAX_AGE = 14 * 86400
PAGE_SIZE = 250
QUERY = """query($id:ID!,$after:ID){ title(id:$id){ id episodes{ episodes(first:250,after:$after){ total
  pageInfo{hasNextPage endCursor} edges{node{runtime{seconds}}} } } } }"""


def fetch_series_runtime(title_id):
    """Soma todos os episódios; quando algum runtime falta, estima só os ausentes pela média."""
    after = None
    total = None
    seconds = 0
    known = 0
    cursor_seen = set()
    while True:
        response = requests.post(IMDB_URL, json={"query": QUERY, "variables": {"id": title_id, "after": after}},
                                 headers=IMDB_HEADERS, timeout=40)
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError("IMDb não retornou os episódios: " + str(payload["errors"][:1]))
        title = (payload.get("data") or {}).get("title") or {}
        connection = ((title.get("episodes") or {}).get("episodes") or {})
        if title.get("id") != title_id or not isinstance(connection.get("edges"), list):
            raise RuntimeError("IMDb retornou uma lista incompleta de episódios.")
        if total is None:
            total = connection.get("total")
            if not isinstance(total, int):
                raise RuntimeError("IMDb não informou o total de episódios.")
        for edge in connection["edges"]:
            runtime = (((edge.get("node") or {}).get("runtime") or {}).get("seconds") or 0)
            if isinstance(runtime, (int, float)) and runtime > 0:
                seconds += int(runtime)
                known += 1
        page = connection.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
        if not after or after in cursor_seen:
            raise RuntimeError("Paginação de episódios incompleta no IMDb.")
        cursor_seen.add(after)
    if total is None or total == 0 or known == 0 or known > total:
        raise RuntimeError("Não há durações de episódios suficientes para calcular a série.")
    missing = total - known
    estimated_seconds = seconds + (round(seconds / known) * missing if missing else 0)
    return {"minutes": round(estimated_seconds / 60), "episodes": total,
            "known_episodes": known, "missing_episodes": missing,
            "estimated": bool(missing), "checked_at": time.time(), "source": "IMDb episodes"}


def sync_series_runtimes(titles, force=False):
    """Atualiza entradas antigas; falhas individuais deixam a cópia anterior intacta."""
    cache = load_json(PATH, {})
    if not isinstance(cache, dict):
        cache = {}
    now = time.time()
    targets = {t["id"]: t for t in titles if t and t.get("type") in ("tvSeries", "tvMiniSeries")}
    stale = [tid for tid in targets if force or now - (cache.get(tid) or {}).get("checked_at", 0) > MAX_AGE]
    failed = 0
    if stale:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fetch_series_runtime, tid): tid for tid in stale}
            for future in as_completed(futures):
                tid = futures[future]
                try:
                    cache[tid] = future.result()
                except Exception:
                    failed += 1
        save_json(PATH, cache)
    return cache, {"updated": len(stale) - failed, "failed": failed, "total": len(targets)}
