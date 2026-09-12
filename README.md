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
