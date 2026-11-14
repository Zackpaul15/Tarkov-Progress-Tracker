#!/usr/bin/env python3
"""Rebuild the Hideout Rebuild tracker from current tarkov.dev data.

Downloads PvE hideout, trader, task, item and map data, checks it looks sane,
and writes:
  index.html              the standalone page (what GitHub Pages serves)
  build/artifact.html     the same page without the document wrapper
  build/hideout-rebuild.zip   index.html + README.txt, for sending to someone

Standard library only. Usage:
  python tools/refresh.py            download and rebuild
  python tools/refresh.py --cache    reuse files already in build/cache
If the download or the checks fail, nothing is overwritten and the exit code is 1.
"""
import argparse, datetime, functools, json, os, re, sys, urllib.request, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://json.tarkov.dev"
MODE = "pve"
FILES = ["hideout", "traders", "items", "tasks", "maps"]
LANG = ["hideout_en", "traders_en", "items_en", "tasks_en", "maps_en"]
MAIN_TRADERS = ["Prapor", "Therapist", "Skier", "Peacekeeper", "Mechanic", "Ragman", "Jaeger"]
ROUBLES = "5449016a4bdc2d6f028b456f"


def fetch(name, cache_dir, use_cache):
    path = os.path.join(cache_dir, name + ".json")
    if use_cache and os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    last = None
    # Translations are the same for both modes; fall back to the regular set if the PvE path lacks one.
    for mode in ([MODE, "regular"] if name.endswith("_en") else [MODE]):
        url = f"{BASE}/{mode}/{name}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hideout-rebuild-refresh"})
            with urllib.request.urlopen(req, timeout=180) as r:
                raw = r.read()
            data = json.loads(raw)
            if "data" not in data:
                raise ValueError("no data key")
            with open(path, "wb") as f:
                f.write(raw)
            return data
        except Exception as e:  # try the next mode, then give up
            last = f"{url}: {e}"
    raise RuntimeError(last)


def build_data(src):
    items = src["items"]["data"]["items"]
    ie, he, tre, te = (src[k]["data"] for k in ("items_en", "hideout_en", "traders_en", "tasks_en"))
    hid, tr, T = src["hideout"]["data"], src["traders"]["data"], src["tasks"]["data"]
    tasks = T["tasks"]

    maps = {}
    md = src["maps"]["data"]
    md = md.get("maps", md)
    for k, v in md.items():
        if isinstance(v, dict):
            maps[k] = src["maps_en"]["data"].get(v.get("name", ""), v.get("name", k))

    # What the Prestige 1 transfer grid accepts.
    flt = T["prestige"][0]["transferSettings"][0]["itemFilters"]
    allowed_cats, allowed_items = set(flt["allowedCategories"]), set(flt["allowedItems"])

    def transferable(i):
        return i in allowed_items or bool(allowed_cats & set(items.get(i, {}).get("categories", [])))

    skey = {k: v["normalizedName"] for k, v in hid.items()}
    sname = {k: he.get(v["name"], v["name"]) for k, v in hid.items()}
    tname = {k: tre.get(v["name"]) for k, v in tr.items()}
    used = {}

    def reg(i):
        if i not in used:
            it = items.get(i, {})
            used[i] = {"n": ie.get(i + " Name", i), "s": ie.get(i + " ShortName", i),
                       "p": it.get("avg24hPrice") or it.get("lastLowPrice") or 0, "b": it.get("basePrice", 0),
                       "w": it.get("width", 1), "h": it.get("height", 1), "x": 1 if transferable(i) else 0,
                       "u": it.get("wikiLink", "")}
        return i

    pretty = lambda s: re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s or "")
    stations = []
    for k, v in hid.items():
        levels = []
        for l in v["levels"]:
            levels.append({
                "l": l["level"], "t": l["constructionTime"],
                "it": [[reg(r["item"]), r["count"], 1 if (r.get("attributes") or {}).get("foundInRaid") else 0] for r in l["itemRequirements"]],
                "st": [[skey[r["station"]], r["level"]] for r in l["stationLevelRequirements"] if skey[r["station"]] != v["normalizedName"]],
                "sk": [[pretty(r.get("skill") or r.get("name")), r["level"]] for r in l["skillRequirements"]],
                "tr": [[tname.get(r["trader"]), r.get("value", r.get("level"))] for r in l["traderRequirements"]],
            })
        stations.append({"k": v["normalizedName"], "n": sname[k], "lv": levels})

    @functools.lru_cache(None)
    def depth(tid):
        t = tasks.get(tid)
        return 0 if not t else 1 + max([depth(r["task"]) for r in t["taskRequirements"]] or [0])

    traders = []
    for k, v in tr.items():
        name = tname[k]
        if name not in MAIN_TRADERS:
            continue
        lv = [[l["level"], l["requiredPlayerLevel"], l["requiredReputation"]] for l in v["levels"]]
        cand = []
        for tid, t in tasks.items():
            st = sum(s["standing"] for s in t["finishRewards"]["traderStanding"] if s["trader"] == k)
            if st > 0 and t["trader"] == k:
                cand.append((t["minPlayerLevel"] or 0, depth(tid), tid, st))
        cand.sort()
        need, cum, listed = lv[2][2], 0, []
        for pl, _dp, tid, st in cand:  # earliest tasks first, until they cover loyalty level 3
            if cum >= need + 0.3 or len(listed) >= 16:
                break
            t, give = tasks[tid], []
            for o in t["objectives"]:
                if o["type"] == "giveItem" and not o.get("optional"):
                    ids = o.get("items") or []
                    if ids and ids[0] == ROUBLES:
                        continue
                    nm = ie.get(ids[0] + " Name", ids[0]) if ids else "?"
                    if len(ids) > 1:
                        nm += f" (or {len(ids) - 1} alternatives)"
                    give.append([nm, o["count"], 1 if o.get("foundInRaid") else 0])
            mp = sorted({maps.get(m) for o in t["objectives"] for m in (o.get("maps") or []) if maps.get(m)})
            if len(mp) > 3:
                mp = []
            req = [te.get(tasks[r["task"]]["name"]) for r in t["taskRequirements"] if r["task"] in tasks]
            listed.append({"id": tid, "n": te.get(t["name"]), "pl": pl, "r": round(st, 2), "m": mp, "g": give,
                           "u": t.get("wikiLink", ""), "q": [q for q in req if q]})
            cum += st
        traders.append({"n": name, "lv": lv, "tk": listed})
    traders.sort(key=lambda t: MAIN_TRADERS.index(t["n"]))
    return {"stations": stations, "items": used, "traders": traders,
            "fetched": datetime.date.today().isoformat()}


# Item and station ids the page's hand-written parts refer to. If the game renames or removes one, stop.
PAGE_ITEM_IDS = ["59e3606886f77417674759a5", "5b4335ba86f7744d2837a264", "590c311186f77424d1667482",
                 "59faf98186f774067b6be103", "60391b0fb847c71012789415", "5af04b6486f774195a3ebb49",
                 "5e2aedd986f7746d404f3aa4", "5af0534a86f7743b6f354284"]


def check(data, template):
    problems = []
    st = {s["k"]: s for s in data["stations"]}
    if len(st) < 20:
        problems.append(f"only {len(st)} hideout stations")
    if len(data["traders"]) != len(MAIN_TRADERS):
        problems.append(f"{len(data['traders'])} traders, expected {len(MAIN_TRADERS)}")
    for t in data["traders"]:
        if len(t["lv"]) < 4 or not t["tk"]:
            problems.append(f"trader {t['n']} is missing levels or tasks")
    unnamed = [i for i, v in data["items"].items() if v["n"] == i]
    if unnamed:
        problems.append(f"{len(unnamed)} items have no English name")
    for i in PAGE_ITEM_IDS:
        if i not in data["items"]:
            problems.append(f"transfer-plan item {i} is no longer a hideout requirement")
    # Every station level named in the page's recommended order must still exist.
    m = re.search(r"const PRI = \[(.*?)\];", template, re.S)
    for key in re.findall(r"'([a-z-]+:\d)'", m.group(1) if m else ""):
        k, l = key.split(":")
        if k not in st or int(l) > len(st[k]["lv"]):
            problems.append(f"build order names {key}, which the data no longer has")
    # Station requirements must point at stations that exist.
    for s in data["stations"]:
        for l in s["lv"]:
            for k, lvl in l["st"]:
                if k not in st or lvl > len(st[k]["lv"]):
                    problems.append(f"{s['k']} {l['l']} needs unknown {k} {lvl}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", action="store_true", help="reuse downloads already in build/cache")
    args = ap.parse_args()
    build = os.path.join(ROOT, "build")
    cache = os.path.join(build, "cache")
    os.makedirs(cache, exist_ok=True)

    try:
        src = {n: fetch(n, cache, args.cache) for n in FILES + LANG}
        data = build_data(src)
    except Exception as e:
        print(f"REFRESH FAILED, nothing changed: {e}", file=sys.stderr)
        return 1

    template = open(os.path.join(ROOT, "src", "template.html"), encoding="utf-8").read()
    problems = check(data, template)
    if problems:
        print("REFRESH FAILED, nothing changed. The new data did not pass checks:", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        return 1

    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = template.replace("/*DATA*/", blob)
    head, body = page.split('<div class="wrap">', 1)
    doc = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
           '<meta name="viewport" content="width=device-width,initial-scale=1">\n' + head +
           '<style>body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>\n</head>\n<body>\n'
           '<div class="wrap">' + body + '\n</body>\n</html>\n')

    index = os.path.join(ROOT, "index.html")
    old = open(index, encoding="utf-8").read() if os.path.exists(index) else ""
    strip = lambda s: re.sub(r'"fetched":"[^"]*"', "", s)
    changed = strip(old) != strip(doc)
    if changed or not old:
        with open(index, "w", encoding="utf-8", newline="\n") as f:
            f.write(doc)
    with open(os.path.join(build, "artifact.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(page if changed or not old else page.replace(data["fetched"], re.search(r'"fetched":"([^"]*)"', old).group(1)))
    with zipfile.ZipFile(os.path.join(build, "hideout-rebuild.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        z.write(index, "hideout-rebuild/index.html")
        z.write(os.path.join(ROOT, "README.txt"), "hideout-rebuild/README.txt")

    levels = sum(len(s["lv"]) for s in data["stations"])
    print(f"{'UPDATED' if changed else 'NO CHANGE'}: {len(data['stations'])} stations, {levels} upgrade levels, "
          f"{len(data['items'])} items, {sum(len(t['tk']) for t in data['traders'])} tasks, data date {data['fetched']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
