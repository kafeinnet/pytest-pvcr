import io

import pytest

from pytest_pvcr.recordings import EventType, IOPipe, TimelineRecording


def test_iopipe_types():
    rec = TimelineRecording(["cat"])
    rec.saved = True
    stdin = IOPipe(rec, EventType.stdin)
    stdout = IOPipe(rec, EventType.stdout)
    stderr = IOPipe(rec, EventType.stderr)

    with pytest.raises(io.UnsupportedOperation):
        stdin.read()

    with pytest.raises(io.UnsupportedOperation):
        stdin.readline()

    with pytest.raises(io.UnsupportedOperation):
        stdout.write("hello")

    with pytest.raises(io.UnsupportedOperation):
        stderr.write("hello")


def test_iopipe_write():
    rec = TimelineRecording(["cat"])
    rec.saved = True

    p = IOPipe(rec, EventType.stdin)
    p.write(b"hello\n")
    p.write(b"world\n")

    assert rec.next_event().data == b"hello\n"
    assert rec.next_event().data == b"world\n"


def test_iopipe_read():
    rec = TimelineRecording(["cat"])
    rec.append_event(event_type=EventType.stdout, data=b"hello\n")
    rec.saved = True

    p = IOPipe(rec, EventType.stdout)

    assert p.read() == b"hello\n"
    assert p.read() is None


def test_iopipe_readline():
    rec = TimelineRecording(["cat"])
    rec.append_event(event_type=EventType.stdout, data=b"hello\n")
    rec.saved = True

    p = IOPipe(rec, EventType.stdout)

    assert p.readline() == b"hello\n"
    assert p.readline() is None


def test_linked_stdin_pipe():
    rec = TimelineRecording(["cat"])
    linked_stdin = io.BytesIO()

    p = IOPipe(rec, EventType.stdin, real_fd=linked_stdin)
    p.write(b"hello\n")

    assert linked_stdin.getvalue() == b"hello\n"


def test_linked_stdout_pipe():
    rec = TimelineRecording(["cat"])
    linked_stdout = io.BytesIO(b"world\n")

    p = IOPipe(rec, EventType.stdout, real_fd=linked_stdout)

    assert p.read() == b"world\n"
