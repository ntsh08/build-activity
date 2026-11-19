# build-activity

A Claude Code skill that shows a GitHub-style contribution graph of the days you built with Claude, and how many days each project took.

https://github.com/user-attachments/assets/d1547883-5382-4f77-97c6-ac2cb6b12359

Ask Claude "show my build activity" and it opens one page:

- **Build activity:** a green graph of the year. Each square is a day, darker when you worked more with Claude.
- **Activity details:** filter by 1M, 3M, 6M or 1Y to see your projects, what each one is (Mac app, web app, skill…) and how many days each took. Hover a row to magnify its days.

## Install

```bash
npx skills@latest add ntsh08/build-activity --skill build-activity
```

Or copy `skills/build-activity` into `~/.claude/skills/`.

Needs Python 3. No other installs.

## First run

Claude asks one question: which folder holds your projects. Every subfolder becomes a project, and a day counts for a project when you ran Claude Code inside it.

You can then ask Claude to rename a project, merge two folders, add a link or hide a folder.

## Build in more than one tool?

Ask Claude to keep your days in one Markdown file. Claude and Codex then add a line (`date · project · type`) whenever they work on a project, and the page is drawn from that file. You can edit it by hand too.

## Privacy

The skill reads only the date and folder of each saved Claude Code session. It never reads what you said. The page is saved as `build-activity.html` in your projects folder and never leaves your machine.

## License

MIT
