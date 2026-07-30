from __future__ import annotations

import logging
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any

from .recordings import EventType, IOPipe

logger = logging.getLogger("pvcr")

if TYPE_CHECKING:
    from .recordings import Recordings


class PVCRBlockedRunException(Exception): ...


def install_wrapper() -> None:
    sys.modules["subprocess"] = SubprocessWrapper


def uninstall_wrapper() -> None:
    sys.modules["subprocess"] = SubprocessWrapper.pvcr_orig_cls


def run(
    args: list[str] | str,
    *other_args: Any,
    stdin: bytes | str | None = None,
    intput: str | bytes | None = None,
    timeout: int | None = None,
    check: bool = False,
    capture_output: bool = False,
    shell: bool = False,
    **other_kwargs: Any,
) -> subprocess.CompletedProcess:
    """Replaces subprocess.run()."""

    stdout_fd = None
    stderr_fd = None
    if capture_output:
        stdout_fd = SubprocessWrapper.pvcr_orig_cls.PIPE
        stderr_fd = SubprocessWrapper.pvcr_orig_cls.PIPE

    process = Popen(
        args,
        *other_args,
        stdin=stdin,
        stdout=stdout_fd,
        stderr=stderr_fd,
        **other_kwargs,
    )
    stdout, stderr = process.communicate(input=input, timeout=timeout)

    if check and process.returncode > 0:
        exc = SubprocessWrapper.pvcr_orig_cls.CalledProcessError(
            returncode=process.returncode,
            cmd=args,
            output=stdout,
            stderr=stdout,
        )
        raise exc

    return SubprocessWrapper.pvcr_orig_cls.CompletedProcess(
        args,
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
    )


class Popen:
    """Replaces subprocess.Popen()"""

    def __init__(self, args: list[str] | str, *other_args: Any, **other_kwargs: Any) -> None:
        self._pvcr_recording = SubprocessWrapper.pvcr_history.append(args)
        self._pvcr_start_time = time.time_ns()
        self.returncode = None

        if self._pvcr_recording.saved:
            logger.debug("Replaying recorded dynamic command: %s", args)

            # link this fake process pipes to the recording ones.
            self.stdin = IOPipe(recording=self._pvcr_recording, event_type=EventType.stdin)
            self.stdout = IOPipe(recording=self._pvcr_recording, event_type=EventType.stdout)
            self.stderr = IOPipe(recording=self._pvcr_recording, event_type=EventType.stderr)

            return

        should_block = SubprocessWrapper.pvcr_block_run or SubprocessWrapper.pvcr_history.block_unrecorded
        if should_block:
            logger.warning("Blocked unrecorded command: %s", args)
            raise PVCRBlockedRunException(f"Blocked unrecorded command: {args}")

        logger.debug("Executing and recording command: %s", args)

        self._real_process = SubprocessWrapper.pvcr_orig_cls.Popen(args, *other_args, **other_kwargs)

        # Link real standard input/outputs to our recording ones
        self.stdin = IOPipe(
            recording=self._pvcr_recording,
            event_type=EventType.stdin,
            real_fd=self._real_process.stdin,
        )
        self.stdout = IOPipe(
            recording=self._pvcr_recording,
            event_type=EventType.stdout,
            real_fd=self._real_process.stdout,
        )
        self.stderr = IOPipe(
            recording=self._pvcr_recording,
            event_type=EventType.stderr,
            real_fd=self._real_process.stderr,
        )

    def _pvcr_write(self):
        # Save the result to the recordings file
        self._pvcr_recording.saved = True

        SubprocessWrapper.pvcr_history.write(self._pvcr_recording)

    def communicate(self, input: str | bytes | None = None, timeout: int | None = None) -> tuple[bytes, bytes]:
        if self._pvcr_recording.saved:
            if input:
                self.stdin.write(input)

            if SubprocessWrapper.pvcr_do_wait:
                # Wait the remaining process time.
                # Duration is in nanoseconds
                max_time = self._pvcr_recording.remaining_duration() / 1000000000
                if timeout:
                    max_time = max(max_time, timeout)

                time.sleep(max(0, max_time))

            self.returncode = self._pvcr_recording.returncode

            ret = (
                self._pvcr_recording.concat_events(EventType.stdout, from_start=False),
                self._pvcr_recording.concat_events(EventType.stderr, from_start=False),
            )

            return ret

        # Wait for the real process to finish and record the result.
        stdout, stderr = self._real_process.communicate(input, timeout)
        self.returncode = self._real_process.returncode

        self._pvcr_recording.returncode = self.returncode

        if stdout:
            self._pvcr_recording.append_event(EventType.stdout, stdout)
        if stderr:
            self._pvcr_recording.append_event(EventType.stderr, stderr)

        self._pvcr_write()

        return stdout if stdout else b"", stderr if stderr else b""

    def wait(self, timeout=None) -> int:
        if self._pvcr_recording.saved:
            if SubprocessWrapper.pvcr_do_wait:
                time.sleep(max(self._pvcr_recording.remaining_duration() / 1000000000, timeout if timeout else 0))

            return self._pvcr_recording.returncode

        rc = self._real_process.wait(timeout)

        self._pvcr_recording.returncode = rc
        self._pvcr_write()

        return rc

    def poll(self) -> int | None:
        if self._pvcr_recording.saved:
            now = time.time_ns()
            if now - self._pvcr_start_time >= self._pvcr_recording.total_duration():
                self.returncode = self._pvcr_recording.returncode
                self._pvcr_write()

            return self.returncode

        ret = self._real_process.poll()
        if ret is not None:
            self._pvcr_recording.returncode = ret

        return ret

    def send_signal(self, signal) -> None:
        if self._pvcr_recording.saved:
            return

        self._real_process.send_signal(signal)

    def terminate(self) -> None:
        if self._pvcr_recording.saved:
            return

        self._real_process.terminate()
        self._pvcr_write()

    def kill(self) -> None:
        if self._pvcr_recording.saved:
            return

        self._real_process.kill()
        self._pvcr_write()


class MetaSubprocessWrapper(type):
    """subprocess class wrapper metaclass."""

    pvcr_orig_cls = subprocess
    pvcr_current_request = None
    pvcr_do_wait: bool = True
    pvcr_record_mode: str = "none"
    pvcr_block_run: bool = False
    pvcr_history: Recordings
    pvcr_enabled: bool = False

    def __getattribute__(cls, item: str) -> Any:
        pvcr_orig_cls = object.__getattribute__(cls, "pvcr_orig_cls")
        pvcr_enabled = object.__getattribute__(cls, "pvcr_enabled")

        if pvcr_enabled and item == "run":
            return run

        if pvcr_enabled and item == "Popen":
            return Popen

        if item == "pvcr_orig_cls":
            return pvcr_orig_cls

        try:
            return object.__getattribute__(cls, item)
        except AttributeError:
            return getattr(pvcr_orig_cls, item)


class SubprocessWrapper(metaclass=MetaSubprocessWrapper): ...
