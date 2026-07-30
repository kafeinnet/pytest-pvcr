import textwrap


def test_pvcr_records_and_replays_popen(pytester):
    pytester.makepyfile(
        textwrap.dedent("""\
        import subprocess
        import pytest

        @pytest.mark.pvcr()
        def test_echo():
            ret = subprocess.Popen(["echo", "hello\\nworld !"], stdout=subprocess.PIPE)
            line1 = ret.stdout.readline()
            line2 = ret.stdout.readline()
            ret.communicate()

            assert ret.returncode == 0
            assert line1 == b"hello\\n"
            assert line2 == b"world !\\n"
        """)
    )
    # First run: record
    result = pytester.runpytest("--pvcr-record-mode=new", "-v")
    result.assert_outcomes(passed=1)

    # Second run: replay (none mode, no real execution)
    result = pytester.runpytest("--pvcr-record-mode=none", "-v")
    result.assert_outcomes(passed=1)


def test_pvcr_records_and_replays_run(pytester):
    pytester.makepyfile(
        textwrap.dedent("""\
        import subprocess
        import pytest

        @pytest.mark.pvcr()
        def test_echo():
            ret = subprocess.run(["echo", "hello"])
            assert ret.returncode == 0
            assert b"hello" in ret.stdout
        """)
    )
    # First run: record
    result = pytester.runpytest("--pvcr-record-mode=new", "-v")
    result.assert_outcomes(passed=1)

    # Second run: replay (none mode, no real execution)
    result = pytester.runpytest("--pvcr-record-mode=none", "-v")
    result.assert_outcomes(passed=1)


def test_pvcr_no_marker_passthrough(pytester):
    pytester.makepyfile(
        textwrap.dedent("""\
        import subprocess

        def test_no_pvcr():
            ret = subprocess.run(
                ["echo", "hello"],
                capture_output=True,
            )
            assert ret.returncode == 0
        """)
    )
    result = pytester.runpytest("-v")
    result.assert_outcomes(passed=1)


def test_pvcr_block_run(pytester):
    pytester.makepyfile(
        textwrap.dedent("""\
        import subprocess
        import pytest

        @pytest.mark.pvcr()
        def test_blocked():
            ret = subprocess.run(["echo", "blocked"])
        """)
    )
    result = pytester.runpytest(
        "--pvcr-record-mode=none",
        "--pvcr-block-run",
        "-v",
    )
    result.assert_outcomes(failed=1)


def test_pvcr_record_mode_none(pytester):
    pytester.makepyfile(
        textwrap.dedent("""\
        import subprocess
        import pytest

        @pytest.mark.pvcr()
        def test_echo():
            ret = subprocess.run(["echo", "hello"])
            assert ret.returncode == 0
        """)
    )
    # Record first
    pytester.runpytest("--pvcr-record-mode=new")
    # Check recording file exists
    recordings = list(pytester.path.glob("recordings/**/*.yaml"))
    assert len(recordings) == 1

    # Run with none mode - should replay fine
    result = pytester.runpytest("--pvcr-record-mode=none", "-v")
    result.assert_outcomes(passed=1)


def test_pvcr_record_mode_once(pytester):
    pytester.makepyfile(
        textwrap.dedent("""\
        import subprocess
        import pytest

        @pytest.mark.pvcr()
        def test_echo():
            ret = subprocess.run(["echo", "hello"])
            assert ret.returncode == 0
            assert b"hello" in ret.stdout
        """)
    )
    # First run: records (file doesn't exist yet)
    result = pytester.runpytest("--pvcr-record-mode=once", "-v")
    result.assert_outcomes(passed=1)

    # Second run: replays (file exists now)
    result = pytester.runpytest("--pvcr-record-mode=once", "-v")
    result.assert_outcomes(passed=1)


def test_pvcr_record_mode_once_blocks_new(pytester):
    pytester.makepyfile(
        test_first=textwrap.dedent("""\
        import subprocess
        import pytest

        @pytest.mark.pvcr()
        def test_echo():
            ret = subprocess.run(["echo", "hello"])
            assert ret.returncode == 0
        """),
        test_second=textwrap.dedent("""\
        import subprocess
        import pytest

        @pytest.mark.pvcr()
        def test_echo():
            ret = subprocess.run(["echo", "hello"])
            # Now try an unrecorded command
            ret2 = subprocess.run(["echo", "new_command"])
        """),
    )
    # First run: record with first test file
    result = pytester.runpytest("test_first.py", "--pvcr-record-mode=once", "-v")
    result.assert_outcomes(passed=1)

    # Copy recording for second test (same test name)
    import shutil

    src_dir = pytester.path / "recordings" / "test_first"
    dst_dir = pytester.path / "recordings" / "test_second"
    shutil.copytree(src_dir, dst_dir)

    # Second run with new command should fail
    result = pytester.runpytest("test_second.py", "--pvcr-record-mode=once", "-v")
    result.assert_outcomes(failed=1)
