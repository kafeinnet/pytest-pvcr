import re
from pathlib import Path
from typing import Any

from yaml import dump, load

try:
    from yaml import CDumper as Dumper
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Dumper, Loader


FUZZY_PLACEHOLDER = "[[FUZZY_VALUE]]"


class Recording:
    args: list[str | bytes]
    stdin: str | bytes | None
    stdout: str | bytes | None
    stderr: str | bytes | None
    rc: int | None
    duration: int | None
    iteration: int
    saved: bool

    def __init__(
        self,
        args: list[str | bytes],
        stdin: str | bytes | None = None,
        stdout: str | bytes | None = None,
        stderr: str | bytes | None = None,
        rc: int | None = None,
        duration: int | None = None,
        iteration: int = 1,
        saved: bool = False,
    ):
        self.args = args
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.rc = rc
        self.duration = duration
        self.iteration = iteration
        self.saved = saved

    def to_encoded_dict(self) -> dict[str, Any]:
        """Generate a dictionnary with this record data.

        Returns:
            a dictionnary
        """
        ret = {
            "args": self.args,
            "rc": self.rc,
            "duration": self.duration,
            "iteration": self.iteration,
        }

        if self.stdin is not None:
            ret["stdin"] = self.stdin

        if self.stdout is not None:
            ret["stdout"] = self.stdout

        if self.stderr is not None:
            ret["stderr"] = self.stderr

        return ret

    @classmethod
    def from_encoded_dict(self, data: dict[str, Any]) -> "Recording":
        """Create a Recording instance from a dictionnary of data.

        Args:
            data: a dictionnary

        Returns:
            a Recording
        """
        ret = Recording(
            data.get("args", []),
            rc=data.get("rc", None),
            iteration=data.get("iteration", 1),
        )

        if "stdin" in data:
            ret.stdin = data.get("stdin")

        if "stdout" in data:
            ret.stdout = data.get("stdout")

        if "stderr" in data:
            ret.stderr = data.get("stderr")

        if "rc" in data:
            ret.rc = data.get("rc")

        if "duration" in data:
            ret.duration = data.get("duration")

        return ret

    def copy(self, other: "Recording") -> None:
        """Copy a Recording into this one.

        Args:
            other: another Recording
        """
        self.args = other.args
        self.stdin = other.stdin
        self.stdout = other.stdout
        self.stderr = other.stderr
        self.rc = other.rc
        self.iteration = other.iteration
        self.duration = other.duration

    def match(
        self, args: list[str], stdin: str | None = None, iteration: int | None = None
    ) -> bool:
        """Match to recordings.

        Args:
            args: a list of command line arguments
            stdin: an stdin value
            iteration: an iteration number

        Returns:
            True if this recording match args, stdin and iteration number
        """
        # Todo fuzzy match here
        return (
            self.args == args
            and self.stdin == stdin
            and (iteration is None or self.iteration == iteration)
        )

    def __eq__(self, other: "Recording") -> bool:
        """Compare two recordings.

        Args:
            other: other Recording

        Returns:
            True if other's args, stdin and iteration are equals to ours
        """
        return self.match(other.args, other.stdin, other.iteration)


class Recordings:
    def __init__(
        self,
        recordings_file: Path,
        record_mode: str,
        fuzzy_matchers: list[str] | None = None,
    ) -> None:
        self._file = recordings_file
        self._mode = record_mode
        self._fuzzy_matchers = fuzzy_matchers or []

        self._history = []

    def find_all(self, args: list[str], stdin: str | None = None) -> list[Recording]:
        """Find all occurence in history matching provided arguments.

        Args:
            args: a list of command line arguments
            stdin: an stdin value

        Returns:
            A list of recordings matching args and stdin
        """
        ret = []
        for recording in self._history:
            if recording.match(args, stdin):
                ret.append(recording)

        return ret

    def _fuzzy_compiler(self, args: list[str | bytes]) -> list[str]:
        """Add fuzzy matching to a list or args.

        Fuzzy matching is accomplished by replacing some regex or non-matching part of some regex
        with a placeholder string.

        Args:
            args: a list of args

        Returns:
            a fuzzy matchable list of args
        """
        f_args = []
        for arg in args:
            f_arg = str(arg)

            for f_matcher in self._fuzzy_matchers:
                f_re = re.compile(f_matcher)

                # If the regex has match group, we replace all the matched part with the placeholder
                # Otherwise, the non-matching parts are replaced and the matched parts are kept.
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

    def append(self, args: list[str], stdin: str | None = None) -> Recording:
        """Append a command line to this list of recordings.

        Fill the recording with saved data if a recording matching the parameters exists in the recordings file.

        Args:
            args: a list of command line arguments
            stdin: an stdin value

        Returns:
            The new Recording object
        """
        # Fuzzy matching
        f_args = self._fuzzy_compiler(args)

        new_recording = Recording(f_args, stdin)
        new_recording.iteration = len(self.find_all(f_args, stdin)) + 1
        self.load(new_recording)

        if self._mode == "all":
            new_recording.saved = False

        self._history.append(new_recording)

        return new_recording

    def load(self, recording: Recording) -> None:
        """Load a recording's data from the recordings file.

        Args:
            recording: a Recording to load.
        """
        if not self._file.exists():
            return

        data = load(self._file.open("r"), Loader=Loader)

        if not data or not data.get("recordings", []):
            return

        for s_recording in data.get("recordings", []):
            # self._history.append(Recording.from_encoded_dict(recording))
            o_recording = Recording.from_encoded_dict(s_recording)
            if recording == o_recording:
                recording.copy(o_recording)
                recording.saved = True
                break

    def write(self, recording: Recording) -> None:
        """Write recordings's data to the recordings file.

        Args:
            recording: a Recording to write.
        """
        if self._mode == "none":
            return

        if not self._file.parent.exists():
            self._file.parent.mkdir(parents=True)

        data = {}
        if self._file.exists():
            data = load(self._file.open("r"), Loader=Loader)

        if data is None or "recordings" not in data:
            data = {"recordings": []}

        idx = 0
        for r_idx in range(len(data.get("recordings"))):
            o_recording = Recording.from_encoded_dict(data["recordings"][r_idx])
            if recording != o_recording:
                continue

            if self._mode == "all":
                idx = r_idx
                break
        else:
            idx = len(data.get("recordings"))

        data["recordings"][idx:] = [recording.to_encoded_dict()]

        with self._file.open("w+") as rf:
            rf.write(dump(data, Dumper=Dumper))

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
