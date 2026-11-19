# build-activity

A Claude Code skill that shows a GitHub-style contribution graph of the days you built with Claude, and how many days each project took.

Ask Claude "show my build activity" and it opens one page:

- **Build activity:** a green graph of the year. Each square is a day, darker when you worked more with Claude.
- **Show details:** filter by 1M, 3M, 6M or 1Y to see your projects, how many days each took, your longest streak and your longest project. Hover a row to magnify its days.

## Install

```bash
npx skills@latest add ntsh08/build-activity --skill build-activity
```

Or copy `skills/build-activity` into `~/.claude/skills/`.

Needs Python 3. No other installs.

## First run

Claude asks one question: which folder holds your projects. Every subfolder becomes a project, and a day counts for a project when you ran Claude Code inside it.

You can then ask Claude to rename a project, merge two folders, add a link or hide a folder.

## Privacy

The skill reads only the date and folder of each saved Claude Code session. It never reads what you said. The page is saved as `build-activity.html` in your projects folder and never leaves your machine.

## License

MIT
