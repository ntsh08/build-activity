#!/usr/bin/env python3
"""Build a contribution-style page from Claude Code session history.

Reads only three fields from each saved session line: its type, its timestamp
and the folder Claude was running in. It never reads what was said.
"""
import argparse
import base64
import collections
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HOME = os.path.expanduser("~")
SESSIONS = os.path.join(HOME, ".claude", "projects")
STATE = os.path.join(HOME, ".claude", "build-activity")
CONFIG = os.path.join(STATE, "config.json")
OUTPUT = os.path.join(STATE, "build-activity.html")
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "page.html")
SKIP = {"node_modules", ".git", ".next", "build", "dist", "DerivedData", ".venv", "venv", "Pods", ".build", "out", "coverage"}
ICON_NAMES = ["app-icon.png", "appicon.png", "icon.png", "logo.png", "apple-touch-icon.png", "favicon.png", "icon.svg", "logo.svg", "favicon.svg"]


def load_config():
    try:
        with open(CONFIG) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    os.makedirs(STATE, exist_ok=True)
    with open(CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)


def pretty(folder):
    words = [w for w in re.split(r"[-_ .]+", folder) if w]
    return " ".join(w[:1].upper() + w[1:] for w in words) or folder


def is_tool_result(content):
    return isinstance(content, list) and content and all(
        isinstance(x, dict) and x.get("type") == "tool_result" for x in content
    )


def scan(root):
    """Messages per day across all sessions, and active days per top-level folder under root."""
    per_day = collections.Counter()
    folders = collections.defaultdict(set)
    prefix = os.path.realpath(root) + os.sep
    for path in glob.glob(os.path.join(SESSIONS, "**", "*.jsonl"), recursive=True):
        try:
            fh = open(path, errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"user"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("type") != "user" or d.get("isMeta") or d.get("isSidechain"):
                    continue
                ts = d.get("timestamp")
                if not ts or is_tool_result((d.get("message") or {}).get("content")):
                    continue
                try:
                    day = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().date().isoformat()
                except ValueError:
                    continue
                per_day[day] += 1
                cwd = os.path.realpath(d.get("cwd") or "") + os.sep
                if cwd.startswith(prefix) and cwd != prefix:
                    folders[cwd[len(prefix):].split(os.sep)[0]].add(day)
    return per_day, folders


def to_data_uri(path, app):
    ext = path.lower().rsplit(".", 1)[-1]
    if ext == "svg":
        if os.path.getsize(path) > 200_000:
            return None
        with open(path, "rb") as f:
            return "data:image/svg+xml;base64," + base64.b64encode(f.read()).decode()
    src = path
    tmp = None
    if shutil.which("sips"):
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
        r = subprocess.run(["sips", "-s", "format", "png", "-Z", "128", path, "--out", tmp], capture_output=True)
        if r.returncode == 0:
            src = tmp
    elif ext == "icns":
        return None
    try:
        if os.path.getsize(src) > 300_000:
            return None
        with open(src, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


def find_icon(folder):
    """Best guess at a project's real icon: an app icon first, then a logo or non-default favicon."""
    found = []
    base_depth = folder.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(folder):
        if dirpath.count(os.sep) - base_depth >= 5:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in SKIP and not d.startswith(".")]
        for name in filenames:
            low = name.lower()
            full = os.path.join(dirpath, name)
            if dirpath.endswith(".appiconset") and low.endswith(".png"):
                found.append((3, os.path.getsize(full), full, True))
            elif low == "appicon.icns":
                found.append((3, 0, full, True))
            elif low in ICON_NAMES:
                found.append((2 if "icon" in low else 1, 0, full, low.startswith("app")))
    for _, _, path, app in sorted(found, key=lambda x: (-x[0], -x[1])):
        uri = to_data_uri(path, app)
        if uri:
            return uri, app
    return None, False


def find_link(folder):
    try:
        with open(os.path.join(folder, "package.json")) as f:
            home = json.load(f).get("homepage")
        if isinstance(home, str) and home.startswith("http"):
            return home
    except (OSError, ValueError):
        pass
    return None


def build(cfg):
    root = cfg["root"]
    per_day, folders = scan(root)
    rename, merge, links = cfg.get("rename", {}), cfg.get("merge", {}), cfg.get("links", {})
    hidden = set(cfg.get("hide", []))
    groups = collections.defaultdict(lambda: {"days": set(), "folders": []})
    for folder, days in folders.items():
        if folder in hidden or folder.startswith(".") or not os.path.isdir(os.path.join(root, folder)):
            continue
        target = merge.get(folder, folder)
        if target in hidden:
            continue
        groups[target]["days"] |= days
        groups[target]["folders"].append(folder)
    projects = []
    for target, g in groups.items():
        icon, app = None, False
        for folder in [target] + [f for f in g["folders"] if f != target]:
            path = os.path.join(root, folder)
            if os.path.isdir(path):
                icon, app = find_icon(path)
                if icon:
                    break
        link = links.get(target) or find_link(os.path.join(root, target))
        projects.append({
            "name": rename.get(target, pretty(target)),
            "folder": target,
            "days": sorted(g["days"]),
            "icon": icon,
            "app": app,
            "url": link,
        })
    today = datetime.date.today()
    year = int(cfg.get("year") or today.year)
    data = {"year": year, "today": today.isoformat(), "messages": dict(sorted(per_day.items())), "projects": projects}
    with open(TEMPLATE) as f:
        page = f.read()
    os.makedirs(STATE, exist_ok=True)
    with open(OUTPUT, "w") as f:
        f.write(page.replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":"))))
    in_year = [d for d in per_day if d.startswith(str(year))]
    project_days = set().union(*[set(p["days"]) for p in projects]) if projects else set()
    print(f"PAGE {OUTPUT}")
    print(f"{len(in_year)} days building in {year}")
    for p in sorted(projects, key=lambda p: -len(p["days"]))[:8]:
        print(f"- {p['name']}: {len(p['days'])} days ({p['days'][0]} to {p['days'][-1]})")
    loose = len([d for d in per_day if d not in project_days])
    if loose:
        print(f"{loose} days were spent outside any project folder; they count on the graph only.")


def pair(value):
    if "=" not in value:
        sys.exit(f"Expected FOLDER=VALUE, got: {value}")
    k, v = value.split("=", 1)
    return k.strip(), v.strip()


def main():
    ap = argparse.ArgumentParser(description="Build activity from Claude Code sessions")
    ap.add_argument("--root", help="folder that holds your projects (saved for next time)")
    ap.add_argument("--rename", action="append", default=[], metavar="FOLDER=Name")
    ap.add_argument("--merge", action="append", default=[], metavar="FOLDER=TARGET_FOLDER")
    ap.add_argument("--link", action="append", default=[], metavar="FOLDER=URL")
    ap.add_argument("--hide", action="append", default=[], metavar="FOLDER")
    ap.add_argument("--unhide", action="append", default=[], metavar="FOLDER")
    ap.add_argument("--year", type=int)
    args = ap.parse_args()

    cfg = load_config()
    if args.root:
        root = os.path.realpath(os.path.expanduser(args.root))
        if not os.path.isdir(root):
            sys.exit(f"Not a folder: {root}")
        cfg["root"] = root
    for key, items in (("rename", args.rename), ("merge", args.merge), ("links", args.link)):
        for item in items:
            k, v = pair(item)
            cfg.setdefault(key, {})[k] = v
    hide = set(cfg.get("hide", [])) | set(args.hide)
    cfg["hide"] = sorted(hide - set(args.unhide))
    if args.year:
        cfg["year"] = args.year
    if not cfg.get("root"):
        print("NEEDS_ROOT")
        return
    save_config(cfg)
    if not os.path.isdir(SESSIONS):
        sys.exit(f"No Claude Code sessions found at {SESSIONS}")
    build(cfg)


if __name__ == "__main__":
    main()
