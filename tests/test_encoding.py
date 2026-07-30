from pytest_pvcr.recordings import EventType, TimelineRecording, _decode_value, _encode_value


class TestEncodeValue:
    def test_str(self):
        assert _encode_value("hello") == "hello"

    def test_none(self):
        assert _encode_value(None) is None

    def test_bytes(self):
        result = _encode_value(b"hello")

        assert isinstance(result, dict)
        assert "__base64__" in result
        assert result["__base64__"] == "aGVsbG8="


class TestDecodeValue:
    def test_str(self):
        assert _decode_value("hello") == "hello"

    def test_none(self):
        assert _decode_value(None) is None

    def test_bytes(self):
        result = _decode_value({"__base64__": "aGVsbG8="})

        assert result == b"hello"

    def test_regular_dict(self):
        d = {"key": "value"}

        assert _decode_value(d) == d


class TestRoundtrip:
    def test_bytes_roundtrip(self):
        original = b"\x00\x01\x02\xff binary data"

        assert _decode_value(_encode_value(original)) == original

    def test_str_roundtrip(self):
        original = "hello world"

        assert _decode_value(_encode_value(original)) == original


class TestTimelineRecordingBytesEncoding:
    def test_to_encoded_dict_bytes(self):
        rec = TimelineRecording(
            ["cmd"],
            returncode=0,
        )
        rec.append_event(event_type=EventType.stdin, data=b"in")
        d = rec.to_encoded_dict()
        timeline = d.get("timeline")

        assert isinstance(timeline[0]["data"], dict)
        assert "__base64__" in timeline[0]["data"]

    def test_from_encoded_dict_bytes(self):
        d = {
            "args": ["cmd"],
            "timeline": [
                {
                    "data": {"__base64__": "aGVsbG8="},
                    "event_type": 1,
                },
                {
                    "data": {"__base64__": "ZXJy"},
                    "event_type": 2,
                },
            ],
            "returncode": 0,
            "iteration": 1,
        }
        rec = TimelineRecording.from_encoded_dict(d)

        event = rec.next_event(EventType.stdout)
        assert event.data == b"hello"
        event = rec.next_event(EventType.stderr)
        assert event.data == b"err"

    def test_full_roundtrip_bytes(self):
        original = TimelineRecording(
            ["cmd"],
            returncode=0,
            iteration=1,
        )
        original.append_event(event_type=EventType.stdin, data=b"in")
        original.append_event(event_type=EventType.stdout, data=b"out")
        d = original.to_encoded_dict()
        restored = TimelineRecording.from_encoded_dict(d)

        assert restored.timeline[0].data == original.timeline[0].data
        assert restored.timeline[0].data == original.timeline[0].data
        assert restored.timeline[1].data == original.timeline[1].data
