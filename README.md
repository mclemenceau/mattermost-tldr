# mattermost-tldr

Export Mattermost messages to a structured markdown digest and summarize
them with an AI assistant — so you can catch up on busy channels in
seconds instead of scrolling for minutes.

## Introduction

If you happen to use Mattermost a lot, you know the dread of looking at hundreds
of channels with multiple updates waiting and worrying about missing anything.
With **mattermost-tldr** you can export a digest of any given time period into a
markdown file and pass it to your favourite AI model with a custom prompt to
surface what is really important to you.

After a day off?
```
mattermost-tldr --yesterday
```

You start your day 6 hours after your team?
```
mattermost-tldr --hours 6
```

You get the idea :-)

## AI Disclosure

I've developed this project hand in hand with [Claude](https://claude.ai/)
(Anthropic).

While it may have started as a "vibe coding" experiment, I've gradually put in
place several quality gates that run on every change:

- **Linting** — [`ruff`](https://docs.astral.sh/ruff/) enforces code
  style and catches common mistakes
- **Type checking** — [`mypy`](https://mypy-lang.org/) ensures type
  annotations are correct and consistent
- **Tests** — [`pytest`](https://pytest.org/) with a minimum 60% coverage
  threshold, following a test-first approach for bug fixes and new
  features
- **CI** — all of the above run automatically on every push via GitHub
  Actions

I'm planning to continue to expand and support the project while continuing to
learn best practice with AI. I'll likely continue to fine tune `CLAUDE.md` for
example, making this already useful project a continued learning opportunity.

If you're interested in contributing, see [CONTRIBUTING.md](CONTRIBUTING.md).

## How it works

1. **Fetch** — connects to your Mattermost instance and pulls messages
   for the requested time window.
2. **Digest** — writes a structured markdown file grouping messages by
   channel, day and thread.
3. **Summarize** — pipes the digest through an AI backend (GitHub Copilot
   CLI or Claude CLI) using a customizable prompt, and saves the summary
   alongside the digest.

## Requirements

- Python 3.10+
- [`pipx`](https://pipx.pypa.io/) (recommended for installation)
- A Mattermost account with a
  [Personal Access Token](https://developers.mattermost.com/integrate/reference/personal-access-token/)

### AI backend (optional)

By default the tool summarizes the digest automatically using one of:

| Backend | CLI tool | Install |
|---------|----------|---------|
| GitHub Copilot (default) | [`copilot`](https://docs.github.com/en/copilot/using-github-copilot/using-github-copilot-in-the-command-line) | requires a Copilot subscription |
| Claude | [`claude`](https://github.com/anthropics/claude-code) | `npm install -g @anthropic-ai/claude-code` |

**No AI tool? No problem.** Use `--digest-only` to export the markdown
digest without any summarization step. You can then paste the digest into
any AI chat (ChatGPT, Gemini, your company LLM, …) with your own prompt.
You can also run the summary step later on an existing digest file with
`--digest path/to/digest.md`.

## Installation

Install directly from GitHub with `pipx`:

```bash
pipx install git+https://github.com/mclemenceau/mattermost-tldr.git
```

To upgrade later:

```bash
pipx upgrade mattermost-tldr
```

To uninstall:

```bash
pipx uninstall mattermost-tldr
```

## Configuration

### 1. Create your config file

```bash
mkdir -p ~/.config/mattermost-tldr
cp examples/config.example.yaml ~/.config/mattermost-tldr/config.yaml
```

Then edit `~/.config/mattermost-tldr/config.yaml`:

```yaml
server_url: https://mattermost.example.com
token: your_personal_access_token_here   # or use MATTERMOST_TOKEN env var
team: myteam

channels:
  - town-square
  - engineering
```

See [`examples/config.example.yaml`](examples/config.example.yaml) for
the full list of options including `all_channels`, `direct_messages` and
date range defaults.

**Tip:** prefer the environment variable over storing the token in the
file:

```bash
export MATTERMOST_TOKEN=your_token_here
```

### 2. Customize the AI prompt (optional)

On first run the tool writes a default prompt to
`~/.config/mattermost-tldr/prompt.md`. Edit it to focus the summary on
the people and keywords that matter to you. See
[`examples/prompt.md`](examples/prompt.md) for the default prompt.

## Usage

### Common invocations

```bash
# Today's digest + AI summary
mattermost-tldr --today

# Yesterday
mattermost-tldr --yesterday

# This week (Monday → today)
mattermost-tldr --this-week

# Last week (Monday → Sunday)
mattermost-tldr --last-week

# Last N days / last H hours
mattermost-tldr --days 3
mattermost-tldr --hours 4

# All channels you are subscribed to
mattermost-tldr --today --all-channels

# Include direct messages and group DMs
mattermost-tldr --today --direct

# Use Claude instead of GitHub Copilot
mattermost-tldr --today --backend claude
```

### Digest-only mode

Generate the markdown digest without calling any AI backend. Useful when
you want to paste the digest into an AI tool yourself, share it with
someone, or just keep a plain-text log of your channels:

```bash
mattermost-tldr --today --digest-only
```

The digest is written to the `output_dir` defined in your config (default
`./exports`), with a filename like `digest_2026-02-20.md`.

### Summarize an existing digest

Re-run the AI summary on a digest you already generated, or run it after
using `--digest-only`:

```bash
mattermost-tldr --digest exports/digest_2026-02-20.md
mattermost-tldr --digest exports/digest_2026-02-20.md --backend claude
```

### Custom config path

```bash
mattermost-tldr --today --config /path/to/my-config.yaml
```

## Output files

Both files are written to the `output_dir` from your config:

| File | Description |
|------|-------------|
| `digest_<period>.md` | Raw export of messages, grouped by channel and day |
| `summary_<period>.md` | AI-generated summary of the digest |

## Development

```bash
git clone https://github.com/mclemenceau/mattermost-tldr.git
cd mattermost-tldr
make setup       # create .venv and install dev dependencies
make test        # run the test suite
make check       # lint + format check + type check
```
