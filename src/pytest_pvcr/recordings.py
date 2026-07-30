import base64
import io
import logging
import re
import time
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any

from yaml import dump, load

try:
    from yaml import CDumper as Dumper
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Dumper, Loader

logger = logging.getLogger("pvcr")


FUZZY_PLACEHOLDER = "[[FUZZY_VALUE]]"


def _encode_value(value: str | bytes | None) -> str | dict | None:
    """Encode a value for YAML serialization.

    Bytes are stored as base64-encoded strings wrapped in a dict
    to distinguish them from regular strings.
    """
    if isinstance(value, bytes):
        return {"__base64__": base64.b64encode(value).decode("ascii")}
    return value


def _decode_value(value: str | dict | None) -> str | bytes | None:
    """Decode a value from YAML deserialization.

    Detects base64-wrapped dicts and decodes them back to bytes.
    """
    if isinstance(value, dict) and "__base64__" in value:
        return base64.b64decode(value["__base64__"])
    return value


class EventType(IntEnum):
    """Event types."""

    stdin = 0
    stdout = 1
    stderr = 2


@dataclass
class Event:
    """Recorded event.

    Attributes:
        duration: duration of the event in nanoseconds
        event_type: type of event (stdin, stdout or stderr)
        data: recorded buffer data
    """

    duration: int
    event_type: EventType
    data: str | bytes | None

    def to_encoded_dict(self) -> dict[str, Any]:
        """Generate a dictionnary with this record data.

        Returns:
            a dictionnary
        """
        return {
            "duration": self.duration,
            "event_type": self.event_type.value,
            "data": _encode_value(self.data),
        }

    @classmethod
    def from_encoded_dict(self, data: dict) -> "Event":
        """Creates an Event from a saved dictionnary.

        Args:
            data: saved dictionnary

        Returns:
            an Event

        """
        return Event(
            duration=data.get("duration", 0),
            event_type=EventType(data.get("event_type")),
            data=_decode_value(data.get("data")),
        )


class TimelineRecording:
    """A recording of a process.

    Attributes:
        args: process arguments
        timeline: recorded timeline
        saved: True if this recording has been saved in a tape
        returncode: process return code or None if the process is not finished
        iteration: number of time this exact process has been seen in the tape
    """

    def __init__(self, args: str, returncode: int | None = None, iteration: int = 1):
        """Creates a recording.

        Args:
            args: process arguments
            returncode: process return code or None if the process is not finished
            iteration: number of time this exact process has been seen in the tape
        """
        self.args = args
        self.timeline: list[Event] = []
        self.returncode = returncode
        self.iteration = iteration
        self.saved = False
        self._timeline_iterator = {}
        self._start_time = time.time_ns()

    def next_event(self, event_type: EventType) -> Event | None:
        """Return next event.

        Returns:
            next event
        """
        if self._timeline_iterator.get(event_type.value) is None:
            self._timeline_iterator[event_type.value] = 0

        event_num = 0
        for event in self.timeline:
            if event.event_type != event_type:
                continue

            event_num += 1

            if event_num > self._timeline_iterator[event_type]:
                self._timeline_iterator[event_type] = event_num
                return event

        return None

    def remaining_duration(self) -> int:
        """Returns the duration from the current event to the last one.

        Returns:
            a number of nanoseconds
        """
        if not self.timeline:
            return 0

        current_iterator = self._timeline_iterator.copy()
        ret = 0
        for event_type in EventType:
            while event := self.next_event(event_type):
                ret += event.duration

        self._timeline_iterator = current_iterator.copy()

        return ret

    def total_duration(self) -> int:
        """Returns the total duration of the recording.

        Returns:
            a number of nanoseconds
        """
        if not self.timeline:
            return 0

        ret = 0
        for event in self.timeline:
            ret += event.duration

        return ret

    def append_event(
        self,
        event_type: EventType,
        data: str | bytes | None = None,
        duration: int | None = None,
    ) -> None:
        """Append an event to the timeline.

        Args:
            event_type: type of event
            data: event's data
            duration: event's duration
        """
        if duration is None:
            # Get duration of the last event only
            duration = time.time_ns() - self._start_time - self.remaining_duration()

        self.timeline.append(Event(duration=duration, event_type=event_type, data=data))

    def concat_events(self, event_type: EventType, from_start: bool = False) -> bytes:
        """Concatenate data from all remaining events of a particular type.

        Args:
            event_type: type of event
            from_start: if True, concatenate events from the start of the timeline

        Returns:
            concaneted data
        """
        ret = b""

        if from_start:
            self._timeline_iterator[event_type] = 0

        while event := self.next_event(event_type):
            ret += event.data

        return ret

    def match(
        self,
        args: list[str],
        iteration: int | None = None,
    ) -> bool:
        """Match to recordings.

        Args:
            args: a list of command line arguments
            iteration: an iteration number

        Returns:
            True if this recording match args, stdin and iteration number
        """
        return self.args == args and (iteration is None or self.iteration == iteration)

    def __eq__(self, other: object) -> bool:
        """Compare two recordings.

        Args:
            other: other Recording

        Returns:
            True if other's args, stdin and iteration are equals to ours
        """
        if not isinstance(other, TimelineRecording):
            return NotImplemented
        return self.match(other.args, other.iteration)

    def copy(self, other: "TimelineRecording") -> None:
        """Copy a Recording into this one.

        Args:
            other: another Recording
        """
        self.args = other.args
        self.timeline = other.timeline
        self.returncode = other.returncode
        self.iteration = other.iteration

    def to_encoded_dict(self) -> dict[str, Any]:
        """Generate a dictionnary with this record data.

        Returns:
            a dictionnary
        """

        timeline = []
        for event in self.timeline:
            timeline.append(event.to_encoded_dict())

        return {
            "args": self.args,
            "returncode": self.returncode,
            "timeline": timeline,
            "iteration": self.iteration,
        }

    @classmethod
    def from_encoded_dict(cls, data: dict[str, Any]) -> "TimelineRecording":
        """Create a Recording instance from a dictionnary of data.

        Args:
            data: a dictionnary

        Returns:
            a Recording
        """
        recording = TimelineRecording(
            data.get("args", []),
            returncode=data.get("returncode"),
            iteration=data.get("iteration", 1),
        )

        for event in data.get("timeline", []):
            recording.timeline.append(Event.from_encoded_dict(event))

        return recording


class IOPipe(io.IOBase):
    """Recording IO buffer."""

    def __init__(
        self,
        recording: TimelineRecording,
        event_type: EventType,
        do_wait: bool | None = None,
        real_fd: io.IOBase | None = None,
    ) -> None:
        """Creates an IOPipe instance.

        Args:
            recording: recording to add events to
            event_type: type of events expected by this pipe (stdin, stdout or stderr)
            do_wait: if True, wait the recorded time on read events
            real_fd: recorded real file descriptor
        """
        self._recording = recording
        self._event_type = event_type
        self._do_wait = do_wait
        self._real_fd = real_fd

    def write(self, buf: bytes | str) -> None:
        """Write data to the buffer.

        If this pipe is linked to an unsaved recording,
        a write event is added the the recording's timeline.

        Args:
            buf: data to write in the buffer

        Raises:
            io.UnsupportedOperation: this event is an stdin event
        """
        if self._event_type != EventType.stdin:
            raise io.UnsupportedOperation("write")

        self._recording.append_event(event_type=self._event_type, data=buf)

        if self._real_fd:
            self._real_fd.write(buf)

    def writable(self) -> bool:
        """Returns True if the pipe is writable."""
        return self._event_type == EventType.stdin

    def readable(self) -> bool:
        """Returns True if the pipe is readable."""
        return self._event_type != EventType.stdin

    def _generic_read(self, func: str, size: int = -1) -> bytes:
        """Generic function that read or readline a buffer.

        Args:
            func: "read" or "readline"
            size: read up to size bytes from the object.

        Returns:
            read data

        Raises:
            io.UnsupportedOperation: this pipe is not readable
        """
        if not self.readable():
            raise io.UnsupportedOperation(func)

        if self._recording.saved:
            event = self._recording.next_event(self._event_type)
            if event:
                if self._do_wait:
                    time.sleep(event.duration / 1000000000)

                return event.data

            return b""

        buf = getattr(self._real_fd, func)(size)
        self._recording.append_event(event_type=self._event_type, data=buf)

        return buf

    def read(self, size: int = -1) -> bytes:
        """Read the pipe."""
        return self._generic_read("read")

    def readline(self, size: int = -1) -> bytes:
        """Read one line of the pipe."""
        return self._generic_read("readline")

    def readlines(self, hint: int = -1) -> list[bytes]:
        """Returns a list of lines.

        Args:
            hint: if > 0, read at most that number of lines

        Returns:
            a list of lines
        """
        nb = 0
        ret = []
        while line := self.readline():
            ret.append(line)
            nb += 1
            if hint > 0 and nb == hint:
                break

        return ret

    def fileno(self) -> int:
        """Returns the underlying file descriptor if this pipe is linked to a real one."""
        if self._real_fd:
            return self._real_fd.fileno()

        return self._event_type.value


class Recordings:
    def __init__(
        self,
        recordings_file: Path,
        record_mode: str,
        fuzzy_matchers: list[str] | None = None,
    ) -> None:
        self._file = recordings_file
        self._mode = record_mode
        self._fuzzy_matchers = [re.compile(m) for m in (fuzzy_matchers or [])]
        self._file_existed_at_init = recordings_file.exists()

        self._history = []

    @property
    def block_unrecorded(self) -> bool:
        """Return True if unrecorded commands should be blocked.

        In 'once' mode, block when the recording file already existed at init.
        """
        return self._mode == "once" and self._file_existed_at_init

    def find_all(self, args: list[str]) -> list[TimelineRecording]:
        """Find all occurence in history matching provided arguments.

        Args:
            args: a list of command line arguments

        Returns:
            A list of recordings matching args
        """
        ret = []
        for recording in self._history:
            if recording.match(args):
                ret.append(recording)

        return ret

    def _fuzzy_compiler(self, args: list[str | bytes]) -> list[str]:
        """Add fuzzy matching to a list or args.

        Fuzzy matching is accomplished by replacing some regex or
        non-matching part of some regex with a placeholder string.

        Args:
            args: a list of args

        Returns:
            a fuzzy matchable list of args
        """
        f_args = []
        for arg in args:
            f_arg = str(arg)

            for f_re in self._fuzzy_matchers:
                # If the regex has match group, we replace all the
                # matched part with the placeholder. Otherwise, the
                # non-matching parts are replaced and the matched
                # parts are kept.
                if f_re.groups == 0:
                    f_arg = f_re.sub(FUZZY_PLACEHOLDER, f_arg)
                    continue

                f_match = f_re.fullmatch(f_arg)
                if not f_match:
                    continue

                f_arg_len = len(f_arg)
                f_arg = FUZZY_PLACEHOLDER.join(f_match.groups())

                # Add a placeholder if the first matching part is not at the start
                if f_match.start(1) > 0:
                    f_arg = f"{FUZZY_PLACEHOLDER}{f_arg}"

                # Add a placeholder if the last matching part is not at the end
                if f_match.end(f_match.lastindex) < f_arg_len:
                    f_arg = f"{f_arg}{FUZZY_PLACEHOLDER}"

            f_args.append(f_arg)

        return f_args

    def append(self, args: list[str]) -> TimelineRecording:
        """Append a command line to this list of recordings.

        Fill the recording with saved data if a recording matching
        the parameters exists in the recordings file.

        Args:
            args: a list of command line arguments

        Returns:
            The new Recording object
        """
        # Fuzzy matching
        f_args = self._fuzzy_compiler(args)

        new_recording = TimelineRecording(f_args)
        new_recording.iteration = len(self.find_all(f_args)) + 1
        self.load(new_recording)

        if self._mode == "all":
            new_recording.saved = False

        self._history.append(new_recording)

        return new_recording

    def load(self, recording: TimelineRecording) -> None:
        """Load a recording's data from the recordings file.

        Args:
            recording: a TimelineRecording to load.
        """
        if not self._file.exists():
            return

        with self._file.open("r") as f:
            data = load(f, Loader=Loader)

        if not data or not data.get("recordings", []):
            return

        for s_recording in data.get("recordings", []):
            o_recording = TimelineRecording.from_encoded_dict(s_recording)
            if recording == o_recording:
                logger.debug("Loaded recording from %s: %s", self._file, recording.args)
                recording.copy(o_recording)
                recording.saved = True
                break

    def write(self, recording: TimelineRecording) -> None:
        """Write recordings's data to the recordings file.

        Args:
            recording: a TimelineRecording to write.
        """
        skip_write = self._mode == "none" or (self._mode == "once" and self._file_existed_at_init)
        if skip_write:
            logger.debug(
                "Skipping write in '%s' record mode: %s",
                self._mode,
                recording.args,
            )
            return

        if not self._file.parent.exists():
            self._file.parent.mkdir(parents=True)

        data = {}
        if self._file.exists():
            with self._file.open("r") as f:
                data = load(f, Loader=Loader)

        if data is None or "recordings" not in data:
            data = {"recordings": []}

        idx = 0
        for r_idx in range(len(data.get("recordings"))):
            o_recording = TimelineRecording.from_encoded_dict(data["recordings"][r_idx])
            if recording != o_recording:
                continue

            if self._mode == "all":
                idx = r_idx
                break
        else:
            idx = len(data.get("recordings"))

        data["recordings"][idx : idx + 1] = [recording.to_encoded_dict()]

        with self._file.open("w+") as rf:
            rf.write(dump(data, Dumper=Dumper))

        logger.debug("Wrote recording to %s: %s", self._file, recording.args)
        recording.saved = True

    def clean(self, write: bool = False) -> None:
        """Clean the list of recordings.

        Args:
            write: if True, also clean the recordings file.
        """
        self._history = []

        if not write:
            return

        with self._file.open("w+") as rf:
            rf.write(dump({"recordings": []}, Dumper=Dumper))
