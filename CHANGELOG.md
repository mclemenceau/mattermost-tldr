# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

### Changed

### Fixed

---

## [0.1.1] - 2026-02-22

### Fixed

- Correct tag re-release; no source changes relative to v0.1.0.

---

## [0.1.0] - 2026-02-22

### Added

- Initial release.
- CLI entrypoint `mattermost-tldr` with `--today`, `--yesterday`,
  `--this-week`, `--last-week`, `--days N`, and `--hours N` date-range flags.
- `--all-channels` flag to include all subscribed channels.
- `--direct` flag to include direct messages and group DMs.
- `--digest-only` flag to skip AI summarization.
- `--digest PATH` flag to re-summarize an existing digest file.
- `--backend` flag to select between `copilot` (default) and `claude` AI backends.
- `--prompt` flag to override the AI prompt with a named preset or file path.
- `--config PATH` flag for a non-default config file location.
- Automatic prompt file creation at `~/.config/mattermost-tldr/prompt.md` on first run.
- YAML configuration file support (`server_url`, `token`, `team`, `channels`, `output_dir`).
- GitHub Actions CI workflow (ruff, black, mypy, pytest).

---

[Unreleased]: https://github.com/mclemenceau/mattermost-tldr/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/mclemenceau/mattermost-tldr/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mclemenceau/mattermost-tldr/releases/tag/v0.1.0
