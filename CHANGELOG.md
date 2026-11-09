# Changelog

Notable changes to this project. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-08

First public version.

### Added
- `probe` and `entered`, the two calls production code sees.
- Five verdicts, because reachable/unreachable loses the useful part.
- Registry and session.
- A gate that refuses to let a finding be configured away.
- Helpdesk demo with the early return that orphans its own feature; CI asserts that it fails, and for the stated reasons.

[Unreleased]: https://github.com/Dowgg18/covered-but-unreachable/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Dowgg18/covered-but-unreachable/releases/tag/v0.1.0
