# Design Notes — mattermost-tldr

## Module responsibilities

| Module | Responsibility |
|---|---|
| `config.py` | Constants (`DEFAULT_PROMPT`, `CONFIG_DIR`, `PROMPT_FILE`, `DEFAULT_CONFIG`), prompt-file management (`ensure_prompt_file`, `resolve_prompt_file`), YAML config loading (`load_config`) |
| `client.py` | `MattermostClient` — all HTTP calls to the Mattermost API v4 |
| `render.py` | Convert raw post dicts to LLM-optimised Markdown (`render_post`, `render_channel_markdown`, timestamp helpers) |
| `summary.py` | AI backend registry (`BACKENDS`) and `run_ai_summary` orchestration |
| `cli.py` | Date-range resolution (`date_range_from_args`), argument parser (`build_arg_parser`), and `main()` entry point |

## Import dependency graph (no cycles)

```
config  ←─── summary
                ↑
client  ←─── render
                ↑
config, client, render, summary  ←─── cli
```

## Config and prompt file locations

All persistent user data lives under `~/.config/mattermost-tldr/`:

| File | Purpose |
|---|---|
| `~/.config/mattermost-tldr/config.yaml` | Server URL, token, team, channel list, output directory |
| `~/.config/mattermost-tldr/prompt.md` | Default system prompt prepended to every AI summary request |
| `~/.config/mattermost-tldr/<name>.md` | Named prompt preset, selectable via `--prompt <name>` |

`ensure_prompt_file()` creates `prompt.md` from `DEFAULT_PROMPT` on first run.
Edit it to tailor summaries to your workflow (people to watch, keywords, etc.).

`resolve_prompt_file(name_or_path)` resolves the `--prompt` argument:
1. Uses the argument as a literal file path if the file exists.
2. Otherwise looks for `~/.config/mattermost-tldr/<name_or_path>.md`
   (`.md` is appended automatically when not already present).
3. Exits with a clear error if neither location exists.

## Adding a new AI backend

1. Add an entry to `BACKENDS` in `src/mattermost_tldr/summary.py`:

```python
BACKENDS: dict[str, dict] = {
    ...
    "mybackend": {
        "cmd": ["mybackend-cli", "--flag"],
        "input_mode": "stdin",   # or "file"
        "label": "My Backend",
    },
}
```

2. `input_mode` controls how the digest is passed to the subprocess:
   - `"stdin"` — full prompt + digest is written to the process's stdin
     (`subprocess.run(..., input=full_message, ...)`)
   - `"file"` — digest is written to a temp file; the path is appended to
     the CLI command as a `--prompt` argument

3. The new key is automatically accepted by `--backend` in the argument
   parser (it uses `choices=list(BACKENDS)`).

4. Add a test case in `tests/test_summary.py` following the existing
   `TestRunAiSummaryStdin` / `TestRunAiSummaryFile` patterns.
