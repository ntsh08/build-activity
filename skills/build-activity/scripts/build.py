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


WEB_DEPS = ("next", "vite", "react", "vue", "svelte", "@sveltejs/kit", "astro", "nuxt", "@angular/core")


def read(path, limit=200_000):
    try:
        with open(path, errors="ignore") as f:
            return f.read(limit)
    except OSError:
        return ""


def find_kind(folder):
    """Guess what a project is from its files: an app, a skill, a website and so on."""
    seen = set()
    base_depth = folder.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(folder):
        if dirpath.count(os.sep) - base_depth >= 4:
            dirnames[:] = []
        for d in dirnames:
            if d.endswith(".xcodeproj"):
                sdk = set(re.findall(r"SDKROOT = (\w+)", read(os.path.join(dirpath, d, "project.pbxproj"))))
                seen |= {"ios"} if "iphoneos" in sdk else {"mac"} if "macosx" in sdk else set()
            if d == ".claude-plugin":
                seen.add("plugin")
        dirnames[:] = [d for d in dirnames if d not in SKIP and not d.startswith(".") and d != "scripts"]
        for name in filenames:
            full = os.path.join(dirpath, name)
            if name == "SKILL.md":
                seen.add("skill")
            elif name == "Package.swift":
                t = read(full)
                seen.add("ios" if ".iOS" in t and ".macOS" not in t else "mac" if ".macOS" in t else "swift")
            elif name.endswith(".swift"):
                t = read(full, 4000)
                if "import AppKit" in t:
                    seen.add("mac-code")       # weak: could be a helper script
                elif "import UIKit" in t:
                    seen.add("ios-code")
            elif name == "Info.plist" and "LSMinimumSystemVersion" in read(full):
                seen.add("mac")
            elif name == "manifest.json" and '"manifest_version"' in read(full):
                seen.add("extension")
            elif name == "package.json":
                try:
                    pj = json.loads(read(full))
                except ValueError:
                    pj = {}
                deps = {**pj.get("dependencies", {}), **pj.get("devDependencies", {})}
                if "electron" in deps:
                    seen.add("desktop")
                elif any(k in deps for k in WEB_DEPS):
                    seen.add("web")
                elif pj.get("bin"):
                    seen.add("cli")
            elif name == "index.html":
                seen.add("web")
    order = [("ios", "iOS app"), ("mac", "Mac app"), ("desktop", "Desktop app"), ("plugin", "Plugin"),
             ("skill", "Skill"), ("extension", "Browser extension"), ("ios-code", "iOS app"), ("mac-code", "Mac app"),
             ("web", "Web app"), ("cli", "CLI")]
    return next((label for key, label in order if key in seen), None)


def find_link(folder):
    try:
        with open(os.path.join(folder, "package.json")) as f:
            home = json.load(f).get("homepage")
        if isinstance(home, str) and home.startswith("http"):
            return home
    except (OSError, ValueError):
        pass
    return None


RECORD_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}) · (.+?)(?: · (.+?))?\s*$")
RECORD_HEADER = ("# Activity\n\nOne line per day per project: date · project · type.\n"
                 "Added by the build-activity skill. Fix or add lines by hand any time.\n\n")


def history_groups(cfg):
    """Days per project from Claude Code's saved sessions, with merges and hidden folders applied."""
    root = cfg["root"]
    per_day, folders = scan(root)
    merge, hidden = cfg.get("merge", {}), set(cfg.get("hide", []))
    groups = collections.defaultdict(lambda: {"days": set(), "folders": []})
    for folder, days in folders.items():
        if folder in hidden or folder.startswith(".") or not os.path.isdir(os.path.join(root, folder)):
            continue
        target = merge.get(folder, folder)
        if target in hidden:
            continue
        groups[target]["days"] |= days
        groups[target]["folders"].append(folder)
    return per_day, groups


def member_folders(cfg, target):
    return [target] + [f for f, t in cfg.get("merge", {}).items() if t == target and f != target]


def project_kind(cfg, target):
    kind = cfg.get("kind", {}).get(target)
    if kind:
        return kind
    for folder in member_folders(cfg, target):
        path = os.path.join(cfg["root"], folder)
        kind = find_kind(path) if os.path.isdir(path) else None
        if kind:
            return kind
    return None


def project_name(cfg, target):
    return cfg.get("rename", {}).get(target, pretty(target))


def folder_for(cfg, name):
    """The project folder behind a display name in the record."""
    for folder, shown in cfg.get("rename", {}).items():
        if shown == name:
            return folder
    root = cfg["root"]
    for folder in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        if pretty(folder) == name or folder == name:
            return cfg.get("merge", {}).get(folder, folder)
    return None


def read_record(path):
    entries = []
    try:
        with open(path) as f:
            for line in f:
                m = RECORD_LINE.match(line.strip().lstrip("-* "))
                if m:
                    entries.append((m.group(1), m.group(2).strip(), (m.group(3) or "").strip() or None))
    except OSError:
        pass
    return entries


def save_record(path, lines):
    with open(path, "w") as f:
        f.write(RECORD_HEADER + "\n".join(lines) + ("\n" if lines else ""))


def commit_record(path, message):
    """If the record sits in a git repo, commit it and push quietly. Failures never block."""
    folder = os.path.dirname(path)
    try:
        if subprocess.run(["git", "-C", folder, "rev-parse"], capture_output=True).returncode != 0:
            return
        subprocess.run(["git", "-C", folder, "add", path], capture_output=True, timeout=20)
        subprocess.run(["git", "-C", folder, "commit", "-q", "-m", message, "--", path], capture_output=True, timeout=20)
        subprocess.run(["git", "-C", folder, "push", "-q"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass


def start_record(cfg, path):
    """Create the record, filled with every day already in Claude Code's history."""
    if read_record(path):
        return
    _, groups = history_groups(cfg)
    lines = []
    for target, g in groups.items():
        name, kind = project_name(cfg, target), project_kind(cfg, target)
        lines += [f"{d} · {name}" + (f" · {kind}" if kind else "") for d in g["days"]]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    save_record(path, sorted(lines))
    commit_record(path, "Start the activity record")
    print(f"RECORD {path} ({len(lines)} lines from Claude Code history)")


def log_today(cfg, project):
    """Add today's line for a project to the record, once per day."""
    path = cfg.get("record")
    if not path:
        sys.exit("No record file set. Run with --record <file.md> first.")
    root = cfg["root"]
    rel = os.path.relpath(os.path.realpath(os.path.expanduser(project)), root) if os.path.isabs(os.path.expanduser(project)) else project
    folder = rel.split(os.sep)[0]
    if folder in ("", ".", "..") or folder.startswith(".."):
        sys.exit(f"Not a project inside {root}: {project}")
    hidden = set(cfg.get("hide", []))
    target = cfg.get("merge", {}).get(folder, folder)
    if folder in hidden or target in hidden:
        print(f"SKIPPED {folder} is hidden")
        return
    name, kind = project_name(cfg, target), project_kind(cfg, target)
    today = datetime.date.today().isoformat()
    entries = read_record(path)
    if any(d == today and n == name for d, n, _ in entries):
        print(f"ALREADY {today} · {name}")
        return
    line = f"{today} · {name}" + (f" · {kind}" if kind else "")
    lines = [f"{d} · {n}" + (f" · {k}" if k else "") for d, n, k in entries] + [line]
    save_record(path, lines)
    commit_record(path, f"{today}: {name}")
    print(f"LOGGED {line}")


def build(cfg):
    root = cfg["root"]
    links = cfg.get("links", {})
    record = cfg.get("record")
    if record:
        entries = read_record(record)
        per_day = collections.Counter(d for d, _, _ in entries)
        by_name = collections.defaultdict(lambda: {"days": set(), "kind": None})
        for d, n, k in entries:
            by_name[n]["days"].add(d)
            by_name[n]["kind"] = k or by_name[n]["kind"]
        found = [(folder_for(cfg, n), n, v["days"], v["kind"]) for n, v in by_name.items()]
    else:
        per_day, groups = history_groups(cfg)
        found = [(t, project_name(cfg, t), g["days"], project_kind(cfg, t)) for t, g in groups.items()]
    projects = []
    for target, name, days, kind in found:
        icon, app, link = None, False, None
        if target:
            for folder in member_folders(cfg, target):
                path = os.path.join(root, folder)
                if os.path.isdir(path):
                    icon, app = find_icon(path)
                    if icon:
                        break
            link = links.get(target) or find_link(os.path.join(root, target))
        projects.append({"name": name, "folder": target, "days": sorted(days), "icon": icon, "app": app, "url": link, "kind": kind})
    today = datetime.date.today()
    year = int(cfg.get("year") or today.year)
    data = {"year": year, "today": today.isoformat(), "messages": dict(sorted(per_day.items())), "projects": projects}
    with open(TEMPLATE) as f:
        page = f.read()
    output = os.path.join(root, "build-activity.html")
    with open(output, "w") as f:
        f.write(page.replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":"))))
    in_year = [d for d in per_day if d.startswith(str(year))]
    project_days = set().union(*[set(p["days"]) for p in projects]) if projects else set()
    print(f"PAGE {output}")
    print(f"{len(in_year)} days building in {year}" + (f" (from {record})" if record else ""))
    for p in sorted(projects, key=lambda p: -len(p["days"]))[:8]:
        print(f"- {p['name']}{' (' + p['kind'] + ')' if p['kind'] else ''}: {len(p['days'])} days ({p['days'][0]} to {p['days'][-1]})")
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
    ap.add_argument("--kind", action="append", default=[], metavar="FOLDER=Type")
    ap.add_argument("--hide", action="append", default=[], metavar="FOLDER")
    ap.add_argument("--unhide", action="append", default=[], metavar="FOLDER")
    ap.add_argument("--year", type=int)
    ap.add_argument("--record", metavar="FILE.md", help="keep days in this Markdown file and draw the page from it (saved)")
    ap.add_argument("--log", metavar="PROJECT", help="add today's line for this project folder to the record, then stop")
    args = ap.parse_args()

    cfg = load_config()
    if args.root:
        root = os.path.realpath(os.path.expanduser(args.root))
        if not os.path.isdir(root):
            sys.exit(f"Not a folder: {root}")
        cfg["root"] = root
    for key, items in (("rename", args.rename), ("merge", args.merge), ("links", args.link), ("kind", args.kind)):
        for item in items:
            k, v = pair(item)
            cfg.setdefault(key, {})[k] = v
    hide = set(cfg.get("hide", [])) | set(args.hide)
    cfg["hide"] = sorted(hide - set(args.unhide))
    if args.year:
        cfg["year"] = args.year
    if args.record:
        cfg["record"] = os.path.realpath(os.path.expanduser(args.record))
    if not cfg.get("root"):
        print("NEEDS_ROOT")
        return
    save_config(cfg)
    if args.log:
        log_today(cfg, args.log)
        return
    if args.record:
        start_record(cfg, cfg["record"])
    if not cfg.get("record") and not os.path.isdir(SESSIONS):
        sys.exit(f"No Claude Code sessions found at {SESSIONS}")
    build(cfg)


if __name__ == "__main__":
    main()
