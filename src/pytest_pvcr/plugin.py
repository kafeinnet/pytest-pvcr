import os
from pathlib import Path
from typing import Iterator

import pytest
from _pytest.config import Config
from _pytest.config.argparsing import Parser
from _pytest.fixtures import SubRequest
from _pytest.mark.structures import Mark

from .recordings import Recordings
from .wrapper import SubprocessWrapper, install_wrapper, uninstall_wrapper


def pytest_configure(config: Config) -> None:
    config.addinivalue_line("markers", "pvcr: Mark the test as recording processes.")
    config.addinivalue_line(
        "markers",
        "pvcr_fuzzy_matcher(regex): Add a fuzzy matcher regex for PVCR recordings.",
    )

    install_wrapper()


def pytest_unconfigure() -> None:
    uninstall_wrapper()


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("pvcr")
    group.addoption(
        "--pvcr-record-mode",
        action="store",
        default="new",
        choices=("new", "none", "all"),
        help='PVCR record mode. Default to "new".',
    )
    group.addoption(
        "--pvcr-block-run",
        action="store_true",
        default=False,
        help="Block all subprocess.run() execution except recorded ones.",
    )
    group.addoption(
        "--pvcr-fuzzy-matcher",
        action="append",
        help="Add a global fuzzy matcher regex.",
    )
    group.addoption(
        "--pvcr-auto-fuzzy-match",
        action="store_true",
        help="Enable automatic fuzzy matching for test path.",
    )


@pytest.fixture
def pvcr_markers(request: SubRequest) -> list[Mark]:
    """Return the list of all the pvcr markers for a test."""
    return list(request.node.iter_markers(name="pvcr"))


@pytest.fixture(scope="function")
def pvcr_fuzzy_matchers(request: SubRequest) -> list[Mark]:
    """Return the list of all the pvcr_fuzzy_matcher markers for a test."""
    return list(request.node.iter_markers(name="pvcr_fuzzy_matcher"))


@pytest.fixture(scope="function")
def pvcr_global_fuzzy_matchers(request: SubRequest) -> list[str]:
    """Get global fuzzy matchers."""
    return request.config.getoption("--pvcr-fuzzy-matcher") or []


@pytest.fixture(scope="session")
def pvcr_auto_fuzzy_match(request: SubRequest) -> bool:
    """Get automatic fuzzy matching value."""
    return bool(request.config.getoption("--pvcr-auto-fuzzy-match"))


@pytest.fixture(scope="session")
def pvcr_record_mode(request: SubRequest) -> str:
    """Get pvcr-record-mode option value."""
    return request.config.getoption("--pvcr-record-mode") or "none"


@pytest.fixture(scope="session")
def pvcr_block_run(request: SubRequest) -> str:
    """Get pvcr-block-run option value."""
    return request.config.getoption("--pvcr-block-run") or False


@pytest.fixture(scope="module")  # type: ignore
def recordings_dir(request: SubRequest) -> str:
    module = request.node.fspath
    return os.path.join(module.dirname, "recordings", module.purebasename)


@pytest.fixture(autouse=True)
def pvcr(
    request: SubRequest,
    pvcr_markers: list[Mark],
    pvcr_fuzzy_matchers: list[Mark],
    pvcr_global_fuzzy_matchers: list[str],
    pvcr_auto_fuzzy_match: bool,
    recordings_dir: str,
    pvcr_record_mode: str,
    pvcr_block_run: bool,
) -> Iterator[Recordings | None]:
    if not pvcr_markers:
        SubprocessWrapper.pvcr_enabled = False
        yield None
    else:
        SubprocessWrapper.pvcr_enabled = True
        SubprocessWrapper.pvcr_current_request = request
        SubprocessWrapper.pvcr_do_wait = pvcr_markers[0].kwargs.get("wait", True)
        SubprocessWrapper.pvcr_block_run = pvcr_block_run
        recordings_file = (
            Path(request.getfixturevalue("recordings_dir"))
            / f"{request.function.__name__}.yaml"
        )

        fuzzy_matchers = pvcr_global_fuzzy_matchers
        for marker in pvcr_fuzzy_matchers:
            if not marker.args:
                continue

            fuzzy_matchers.append(marker.args[0])

        # Insert automatic fuzzy matcher if requested
        if pvcr_auto_fuzzy_match:
            module = request.node.fspath
            fuzzy_matchers.insert(0, str(Path(module.dirname).parent))

        SubprocessWrapper.pvcr_history = Recordings(
            recordings_file, pvcr_record_mode, fuzzy_matchers
        )
        yield SubprocessWrapper.pvcr_history
