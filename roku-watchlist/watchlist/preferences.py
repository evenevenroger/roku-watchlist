"""Preferências compartilhadas entre o celular e o Roku, com atualização por campo."""
import copy
import os
import re
import threading

from .common import DATA_DIR, load_json, save_json

PATH = os.path.join(DATA_DIR, "preferences.json")
_lock = threading.Lock()
NUMBERS = {"sort": 8, "seen": 1, "kind": 2, "dur": 3, "seriesDur": 8, "ares": 2}
STRINGS = {"lang", "service", "genre", "director", "acat", "ayear", "focus_id", "award_year"}


def _list_id(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[\w:-]{1,100}", value))


def validate_patch(patch):
    if not isinstance(patch, dict) or set(patch) - {"unseen", "home_focus", "lists"}:
        raise ValueError("Preferências inválidas.")
    if "unseen" in patch and type(patch["unseen"]) is not bool:
        raise ValueError("O filtro de não vistos deve ser verdadeiro ou falso.")
    if "home_focus" in patch and not _list_id(patch["home_focus"]):
        raise ValueError("Lista inválida.")
    lists = patch.get("lists", {})
    if not isinstance(lists, dict) or len(lists) > 200:
        raise ValueError("Listas inválidas.")
    for lid, values in lists.items():
        if not _list_id(lid) or not isinstance(values, dict):
            raise ValueError("Lista inválida.")
        for key, value in values.items():
            if key in NUMBERS:
                if type(value) is not int or not 0 <= value <= NUMBERS[key]:
                    raise ValueError("Opção inválida: " + key)
            elif key in STRINGS:
                if not isinstance(value, str) or len(value) > 250:
                    raise ValueError("Opção inválida: " + key)
            else:
                raise ValueError("Opção desconhecida: " + key)
    return patch


def get_preferences():
    with _lock:
        return _read()


def _read():
    data = load_json(PATH, {})
    if not isinstance(data, dict):
        data = {}
    return {"revision": data.get("revision", 0), "unseen": data.get("unseen", False),
            "home_focus": data.get("home_focus", ""), "lists": data.get("lists", {})}


def update_preferences(patch):
    validate_patch(patch)
    with _lock:
        data = _read()
        for key in ("unseen", "home_focus"):
            if key in patch:
                data[key] = patch[key]
        # O filtro global prevalece até ser mudado explicitamente naquela lista.
        if "unseen" in patch:
            for values in data["lists"].values():
                values["seen"] = int(patch["unseen"])
        for lid, values in patch.get("lists", {}).items():
            data["lists"].setdefault(lid, {}).update(values)
        if len(data["lists"]) > 500:
            raise ValueError("Limite de listas atingido.")
        data["revision"] += 1
        save_json(PATH, data)
        return copy.deepcopy(data)
