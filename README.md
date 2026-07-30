# pytest-pvcr

![PyPI version](https://img.shields.io/pypi/v/pytest-pvcr.svg)
![Python versions](https://img.shields.io/pypi/pyversions/pytest-pyvcr.svg)
![License](https://img.shields.io/pypi/l/pytest-pyvcr.svg)

A pytest plugin that records and replays commands executed with `subprocess.run()`, inspired by [VCR.py](https://vcrpy.readthedocs.io/).

## Installation

```text
pip install pytest-pvcr
```

## Usage

Mark your tests with `@pytest.mark.pvcr()` and run them:

```python
import subprocess
import pytest


@pytest.mark.pvcr()
def test_ls():
    ret = subprocess.run(["ls", "/tmp"])
    assert ret.returncode == 0


@pytest.mark.pvcr(wait=False)
def test_slow_command():
    # On replay, pvcr won't sleep for the original command duration
    ret = subprocess.run(["sleep", "10"])
    assert ret.returncode == 0
```

```shell
pytest --pvcr-record-mode=new test_commands.py
```

Recordings are stored as YAML files in `recordings/<module>/<test_name>.yaml`.

### Record modes

```shell
# Only record new commands not previously recorded (default)
pytest --pvcr-record-mode=new

# Replay only, never record
pytest --pvcr-record-mode=none

# Re-record all commands, even previously recorded ones
pytest --pvcr-record-mode=all

# Record on first run, then replay only and block unrecorded commands
pytest --pvcr-record-mode=once
```

The `once` mode is useful in CI: it records everything on the first run (when no recording file exists), then on subsequent runs it replays and raises `PVCRBlockedRunException` if an unrecorded command is encountered.

### Block execution

Block all unrecorded subprocess calls, useful to protect test environments:

```shell
pytest --pvcr-block-run
```

### Fuzzy matching

Fuzzy matching replaces variable parts of commands so recordings stay portable.

**Via CLI** (global, applies to all tests):

```shell
# Ignore `--dry-run` arguments when matching commands
pytest --pvcr-fuzzy-matcher='--dry-run'

# Keep only the filename from a path
pytest --pvcr-fuzzy-matcher='^.+\/(kubeconfig)$'

# Automatically ignore the parent directory of the test file
pytest --pvcr-auto-fuzzy-match
```

**Via marker** (per-test):

```python
@pytest.mark.pvcr()
@pytest.mark.pvcr_fuzzy_matcher(r"^.+\/(config\.yml)$")
def test_with_fuzzy():
    subprocess.run(["cat", "/some/path/config.yml"])
```

If a regex has **no capture groups**, the matched string is replaced with a placeholder.
If a regex has **capture groups**, the captured parts are kept and the rest is replaced.

## Python support

Python >= 3.12

## Authors

* Fabien Dupont <fab+github@kafe-in.net>
