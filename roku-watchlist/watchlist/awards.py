"""Oscar e Cannes a partir dos prêmios registrados no IMDb."""
import re

from .common import state
from .imdb import imdb_query


AWARDS = {
    # evento IMDb, só vencedores?, regras: (categoria, função que reconhece o prêmio)
    "oscar": ("ev0000003", False, [
        ("Melhor filme", lambda t, c, y=0: t == "Oscar" and bool(re.match(
            r"(Best (Motion )?Picture|Outstanding (Motion )?Picture|Outstanding Production)", c))),
        # só roteiro: "Original Story"/"Motion Picture Story" (até os anos 1950) premiavam o argumento
        ("Roteiro", lambda t, c, y=0: t == "Oscar" and bool(re.search(r"Screenplay|Adaptation|Adapted", c))),
        ("Filme internacional", lambda t, c, y=0: t == "Oscar" and bool(
            re.search(r"International Feature|Foreign Language", c))),
        ("Animação", lambda t, c, y=0: t == "Oscar" and "Animated Feature" in c),
        ("Documentário", lambda t, c, y=0: t == "Oscar" and "Documentary" in c and "Short" not in c),
    ]),
    # "Grand Prize of the Festival" foi o prêmio máximo em 1946–54 e 1964–74 (= Palma);
    # nos outros anos o IMDb usa o mesmo nome para o Grand Prix, o segundo prêmio.
    "cannes": ("ev0000147", True, [
        ("Palma de Ouro", lambda t, c, y=0: t == "Palme d'Or" or (
            t == "Grand Prize of the Festival" and c in ("", "Feature Film") and festival_top(y))),
        ("Grand Prix", lambda t, c, y=0: t == "Grand Prize of the Jury" or (
            t == "Grand Prize of the Festival" and c in ("", "Feature Film") and not festival_top(y))),
        ("Prêmio do Júri", lambda t, c, y=0: t == "Jury Prize" and c == ""),
        ("Un Certain Regard", lambda t, c, y=0: t == "Un Certain Regard Award"),
    ]),
    # Berlim: o 2º prêmio se chamava "Special Jury Prize" até 1999; depois, "Jury Grand Prix"
    # / "Grand Jury Prize". O "Jury Prize" existe em 2000-01 e de 2021 em diante.
    "berlim": ("ev0000091", True, [
        ("Urso de Ouro", lambda t, c, y=0: t == "Golden Berlin Bear" and c in (
            "", "Best Film", "Competition", "International Jury", "Best Drama", "Best Comedy",
            "Best Crime or Adventure", "Best Musical")),
        ("Grande Prêmio do Júri", lambda t, c, y=0: t == "Silver Berlin Bear" and (
            c in ("Jury Grand Prix", "Grand Jury Prize", "Special Prize of the Jury")
            or (c == "Special Jury Prize" and y and y <= 1999))),
        ("Prêmio do Júri", lambda t, c, y=0: t == "Silver Berlin Bear" and (
            c == "Jury Prize" or (c == "Special Jury Prize" and y and y >= 2000))),
    ]),
    # Veneza: "Grand Special Jury Prize" de 1983 a 2018 e "Silver Lion - Grand Jury Prize" depois.
    "veneza": ("ev0000681", True, [
        ("Leão de Ouro", lambda t, c, y=0: t == "Golden Lion" and c in ("", "Best Film")),
        ("Grande Prêmio do Júri", lambda t, c, y=0: t == "Grand Special Jury Prize" or (
            t == "Silver Lion" and c == "Grand Jury Prize")),
        ("Prêmio Especial do Júri", lambda t, c, y=0: t == "Special Jury Prize" and c == ""),
    ]),
}
def festival_top(year):
    return bool(year) and (year <= 1954 or 1964 <= year <= 1974)


Q_AWARD_SEARCH = """query($after:String){ advancedTitleSearch(first:250, after:$after,
  constraints:{awardConstraint:{allEventNominations:[{eventId:"%s"%s}]}}){
  pageInfo{hasNextPage endCursor} edges{ node{ title{ id } } } } }"""
Q_AWARD_NOMS = """query($ids:[ID!]!){ titles(ids:$ids){ id
  awardNominations(first:60, filter:{events:["%s"]}){ edges{ node{ isWinner
  award{ text year category{ text } } } } } } }"""


def fetch_awards(group):
    """{imdb_id: [{"c": categoria, "y": ano, "w": venceu}]} a partir dos prêmios do IMDb."""
    event, winners_only, rules = AWARDS[group]
    ids, after = [], None
    q = Q_AWARD_SEARCH % (event, ", winnerFilter:WINNER_ONLY" if winners_only else "")
    while True:
        s = imdb_query(q, {"after": after})["advancedTitleSearch"]
        ids += [e["node"]["title"]["id"] for e in s["edges"]]
        if not s["pageInfo"]["hasNextPage"]:
            break
        after = s["pageInfo"]["endCursor"]
    out = {}
    for i in range(0, len(ids), 100):
        state["step"] = f"Lendo prêmios ({i}/{len(ids)})"
        for t in imdb_query(Q_AWARD_NOMS % event, {"ids": ids[i:i + 100]})["titles"]:
            if not t:
                continue
            found = {}
            for e in (t.get("awardNominations") or {}).get("edges") or []:
                n = e["node"]
                if winners_only and not n["isWinner"]:
                    continue
                a = n["award"] or {}
                text, cat = a.get("text") or "", (a.get("category") or {}).get("text") or ""
                for name, match in rules:
                    if match(text, cat, a.get("year") or 0):
                        prev = found.get(name)
                        if prev:
                            prev["w"] = prev["w"] or bool(n["isWinner"])
                        else:
                            found[name] = {"c": name, "y": a.get("year"), "w": bool(n["isWinner"])}
            if found:
                out[t["id"]] = list(found.values())
    return out


AWARD_NAMES = {"oscar": "Oscar", "cannes": "Cannes", "veneza": "Veneza", "berlim": "Berlim"}
# ícone da faixa do pôster de cada prêmio (roku-channel/images/<ícone>_dark|_gold.png)
AWARD_ICONS = {"oscar": "trophy", "cannes": "palm", "veneza": "lion", "berlim": "bear"}
