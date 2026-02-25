# Changelog

All notable changes to this project will be documented in this file.

## [0.1.2]

### Fixed

- Fix `bytes` values (`stdout`, `stderr`, `stdin`) not surviving YAML serialization roundtrip. Bytes are now base64-encoded for storage and decoded on load, preserving the original type. Backward-compatible with existing `str` recordings (`recordings.py`)
- Fix `stdin` passed as positional argument to `subprocess.run()` instead of keyword argument, causing it to be interpreted as `bufsize` (`wrapper.py`)
- Fix `write()` truncating all recordings after the replaced one in `all` mode by using `[idx:idx+1]` slice instead of `[idx:]` (`recordings.py`)
- Fix global fuzzy matchers list being mutated across tests, causing matchers to accumulate (`plugin.py`)
- Fix `load()` resetting `_history` on every call, breaking iteration tracking for repeated commands (`recordings.py`)
- Fix unclosed file handles when reading YAML recording files (`recordings.py`)
- Fix `capture_output=True` being forced unconditionally, causing `ValueError` when `stdout` or `stderr` were explicitly provided (`wrapper.py`)
- Remove leftover `print()` debug statements from `pvcr` fixture (`plugin.py`)
- Fix `from_encoded_dict` classmethod using `self` instead of `cls` as first parameter (`recordings.py`)
- Fix `__eq__` raising `AttributeError` when comparing `Recording` with non-`Recording` objects (`recordings.py`)
- Add missing teardown in `pvcr` fixture to reset wrapper state after each test (`plugin.py`)
- Fix `pvcr_block_run` fixture return type annotation (`str` → `bool`) and use explicit `bool()` cast (`plugin.py`)
- Fix Recordings history being cleaned each time a Recording is loaded from file (`recordings.py`)

### Added

- Add `once` record mode (`--pvcr-record-mode=once`): records on first run, then replays only and blocks unrecorded commands on subsequent runs (`plugin.py`, `recordings.py`, `wrapper.py`)
- Add structured logging via `logging.getLogger("pvcr")` for command interception, replay, recording, and blocking events (`wrapper.py`, `recordings.py`)
- Add descriptive error message to `PVCRBlockedRunException` including the blocked command (`wrapper.py`)
- Add test suite with 53 tests: unit tests for `Recording`, `Recordings`, encoding, fuzzy matching, and integration tests via `pytester` (`tests/`)
- Add CI workflow (`.github/workflows/ci.yml`): runs ruff lint/format and pytest on Python 3.12/3.13/3.14 for pushes to main and PRs
- Add code coverage reporting with `pytest-cov` in tests and CI (`pyproject.toml`, `.github/workflows/ci.yml`)
- Add `CONTRIBUTING.md` with development setup, commit convention, and project roadmap
- Add security scanning in CI with `bandit` (static analysis) and `pip-audit` (dependency vulnerabilities)

### Changed

- Pre-compile fuzzy matcher regexes once in `Recordings.__init__()` instead of recompiling on every `_fuzzy_compiler` call (`recordings.py`)
- Migrate from deprecated `request.node.fspath` (py.path) to `request.node.path` (pathlib.Path) (`plugin.py`)
- Remove unused `import os` (`plugin.py`)
- Remove unused `hello()` scaffolding function (`__init__.py`)
- Add type annotations to `run()` function parameters and return type (`wrapper.py`)

## [0.1.1] - 2026-02-23

### Added

- Add MIT license file (`LICENSE`)
- Add package metadata to project configuration (`pyproject.toml`)
- Add `ruff` linter and formatter configuration; apply linting and formatting across source files
- Add badges (PyPI version, Python versions, License) to README

### Fixed

- Fix email address in README

### Changed

- Restrict publish workflow to tagged releases only (`v*` tags) instead of every push

## [0.1.0] - 2026-02-20

### Added

- Initial release of pytest-pvcr
- `@pytest.mark.pvcr()` marker to enable recording/replay of `subprocess.run()` calls
- Record modes: `new` (default), `none`, `all`
- `--pvcr-record-mode` and `--pvcr-block-run` CLI options
- Fuzzy matching via `@pytest.mark.pvcr_fuzzy_matcher()` and `--pvcr-fuzzy-matcher`
- YAML-based recording storage
- GitHub Actions workflow for publishing to PyPI
