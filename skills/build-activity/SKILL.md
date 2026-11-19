---
name: build-activity
description: Shows a GitHub-style contribution graph of the days you built with Claude Code, plus how many days each project took. Use when the user asks to see their build activity, what they worked on, how many days a project took, a contribution graph of their Claude Code work, or runs /build-activity.
---

# Build activity

Turns the user's Claude Code session history into one page: a green contribution graph for the year, and an "Activity details" view with each project's working days.

Each subfolder of the user's projects folder is one project. A day counts for a project when Claude Code ran inside that folder on that day.

## Privacy

The script reads only three fields from each saved session line: its type, its timestamp and the folder Claude ran in. It never reads what was said. The page is saved as `build-activity.html` in the user's projects folder and stays on their machine. Say this in one line on the first run.

## Run it

The script sits next to this file at `scripts/build.py`. It needs only Python 3, with no packages.

```bash
python3 -I <this skill's folder>/scripts/build.py
```

- If it prints `NEEDS_ROOT`, ask the user one question: which folder holds their projects (for example `~/code` or `~/Projects`). Then run it again with `--root "<that folder>"`. The folder is saved, so this is asked only once.
- Otherwise it prints `PAGE <path>` followed by a short summary.

## Show it

1. Open the page. In the Claude desktop app, show it in the preview panel. Anywhere else, open it in the default browser: `open "<path>"` on macOS, `xdg-open "<path>"` on Linux, `start "" "<path>"` on Windows.
   - If the current working folder is inside the projects folder rather than the projects folder itself, the app will ask permission to open the page. Say one line first, for example: "Your page is saved in `~/code`, your projects folder. You're inside `app-one`, so the app will ask before opening it. Click Allow."
2. Reply with the summary as 3–5 short bullets: days building this year, the top projects with their day counts, and the note about days outside any project folder if one was printed.

## Changes the user can ask for

Run the script with these flags, then open the page again. Each change is saved for next time.

| User says | Flag |
| --- | --- |
| "Call `tea-time-v2` Tea Time" | `--rename "tea-time-v2=Tea Time"` |
| "Count `tea-time-v2` as part of `tea-time`" | `--merge "tea-time-v2=tea-time"` |
| "Link Tea Time to teatime.app" | `--link "tea-time=https://teatime.app"` |
| "Hide `scratch`" / "Show it again" | `--hide scratch` / `--unhide scratch` |
| "My projects are somewhere else now" | `--root "<folder>"` |
| "Show 2025" | `--year 2025` |

Flags take folder names, not display names. If the user gives a display name, match it to the folder from the last summary or from the config at `~/.claude/build-activity/config.json`.

## What the page shows

- **Graph:** every day of the year, shaded by how much they worked with Claude that day. Hover shows the date and the projects worked on.
- **Show details:** a 1M / 3M / 6M / 1Y filter, four cards (Projects, Active days, Longest streak, Longest project), and one row per project with its working days. 6M and 1Y group days into weeks.
- **Icons and links** are found automatically when a project has an app icon, logo or non-default favicon, or a `homepage` in `package.json`. Otherwise the row shows the project's first letter.

Days when Claude ran outside any project folder count on the graph but in no project row. Mention this if the summary says so, and suggest opening Claude inside the project folder next time.
