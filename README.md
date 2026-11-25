# ehl_urich

Zürich Hackathon competition repo.

## Entire

This repo uses [Entire](https://entire.io) to capture agent sessions alongside
commits: every change traces back to the prompts, transcript, and tool calls
that produced it.

- `entire status` — current session + checkpoint sync target
- `entire blame <file>` — which lines came from which checkpoint
- `entire why <file>:<line>` — jump from a line to the prompt that wrote it
- `entire session resume <branch>` — restore a previous session

Checkpoints publish to `origin` on `git push`. Agent hooks are installed for
Claude Code (`.claude/settings.json`); cross-agent skills live in
`.agents/skills` and are pinned in `skills-lock.json`.

## Setup

Python (uses [uv](https://docs.astral.sh/uv/)):

```bash
uv venv .venv
uv pip install --only-binary=:all: -r requirements.txt
PYTHONIOENCODING=utf-8 .venv/bin/python flowstate/analysis/01_profile.py   # route names contain umlauts
```

Web apps (`app/`, `viz/`):

```bash
(cd app && npm ci) && (cd viz && npm ci)
```

Data is not in git. `flowstate/data/` is archived on Google Drive at `Dhruv-archive/ehl_urich/flowstate/data.tar`.
Restore it with `rclone copy gdrive:Dhruv-archive/ehl_urich/flowstate/data.tar . && tar -xf data.tar -C flowstate/`.
More environment notes: `CONTEXT.md`, section "Environment".

