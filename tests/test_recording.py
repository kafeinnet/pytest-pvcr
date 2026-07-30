from pytest_pvcr.recordings import EventType, TimelineRecording


class TestTimelineRecording:
    def test_defaults(self):
        rec = TimelineRecording(["ls", "/tmp"])
        assert rec.args == ["ls", "/tmp"]
        assert rec.returncode is None
        assert rec.iteration == 1
        assert rec.saved is False

    def test_all_fields(self):
        rec = TimelineRecording(
            ["echo", "hi"],
            returncode=0,
            iteration=2,
        )
        assert rec.returncode == 0
        assert rec.iteration == 2

    def test_remaining_duration(self):
        rec = TimelineRecording(
            ["echo"],
            returncode=0,
        )
        rec.append_event(event_type=EventType.stdin, data="in", duration=1000)
        rec.append_event(event_type=EventType.stdout, data="out", duration=2000)
        rec.next_event(EventType.stdin)

        assert rec.remaining_duration() == 2000

    def test_total_duration(self):
        rec = TimelineRecording(
            ["echo"],
            returncode=0,
        )
        rec.append_event(event_type=EventType.stdin, data="in", duration=1000)
        rec.append_event(event_type=EventType.stdout, data="out", duration=2000)

        assert rec.total_duration() == 3000


class TestToEncodedDict:
    def test_minimal(self):
        rec = TimelineRecording(["ls"])
        d = rec.to_encoded_dict()
        assert d["args"] == ["ls"]
        assert len(d["timeline"]) == 0

    def test_full(self):
        rec = TimelineRecording(
            ["echo"],
            returncode=0,
            iteration=3,
        )
        rec.append_event(event_type=EventType.stdin, data="in", duration=1000)
        rec.append_event(event_type=EventType.stdout, data="out", duration=2000)
        d = rec.to_encoded_dict()
        assert d["timeline"][0]["data"] == "in"
        assert d["timeline"][0]["duration"] == 1000
        assert d["timeline"][1]["data"] == "out"
        assert d["timeline"][1]["duration"] == 2000
        assert d["returncode"] == 0
        assert d["iteration"] == 3


class TestFromEncodedDict:
    def test_roundtrip(self):
        original = TimelineRecording(
            ["echo", "hello"],
            returncode=0,
            iteration=3,
        )
        d = original.to_encoded_dict()
        restored = TimelineRecording.from_encoded_dict(d)
        assert restored.args == original.args
        assert restored.returncode == original.returncode
        assert restored.iteration == original.iteration

    def test_missing_fields(self):
        rec = TimelineRecording.from_encoded_dict({})
        assert rec.args == []
        assert rec.returncode is None
        assert rec.iteration == 1


class TestCopy:
    def test_copy(self):
        src = TimelineRecording(
            ["ls"],
            returncode=0,
            iteration=5,
        )
        src.append_event(event_type=EventType.stdin, data="in", duration=1000)
        dst = TimelineRecording(["placeholder"])
        dst.copy(src)
        assert dst.args == ["ls"]
        assert dst.returncode == 0
        assert dst.iteration == 5
        assert dst.remaining_duration() == 1000


class TestMatch:
    def test_args_only(self):
        rec = TimelineRecording(["ls", "/tmp"])
        assert rec.match(["ls", "/tmp"]) is True

    def test_args_no_match(self):
        rec = TimelineRecording(["ls", "/tmp"])
        assert rec.match(["ls", "/var"]) is False

    def test_with_iteration(self):
        rec = TimelineRecording(["ls"], iteration=2)
        assert rec.match(["ls"], iteration=2) is True
        assert rec.match(["ls"], iteration=1) is False
        assert rec.match(["ls"]) is True  # iteration=None ignores it


class TestEq:
    def test_equal(self):
        a = TimelineRecording(["ls"], iteration=1)
        b = TimelineRecording(["ls"], iteration=1)
        assert a == b

    def test_not_equal(self):
        a = TimelineRecording(["ls"], iteration=1)
        b = TimelineRecording(["ls"], iteration=2)
        assert a != b

    def test_non_recording(self):
        rec = TimelineRecording(["ls"])
        assert rec.__eq__("not a recording") is NotImplemented
