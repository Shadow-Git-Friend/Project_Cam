"""Release hygiene for the desktop binary (roadmap D4).

The Control Center is launched from an icon, and an icon that Execs a compiled
binary shows whatever was last compiled — not what is in the repo. That failed
silently for thirteen days in July 2026: the icon ran a 16 July build while the
sources were 29 July, so the entire session-evidence layer, the SESSIONS/SHOTS
views and the readiness rewrite were unreachable from the app while every test
passed and the app looked normal.

A rebuild reminder in a comment did not prevent it. These tests make the staleness
observable from the same test run the project already lives by, and pin the two
launch-path properties that keep it observable.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "project-cam-desktop"
CHECK = DESKTOP / "check-binary-fresh.sh"
RUN = DESKTOP / "run.sh"
BINARY = DESKTOP / "src-tauri" / "target" / "release" / "project-cam"

#: Everything the binary is compiled from. Kept here as well as in the shell
#: script so a path added to one and forgotten in the other is caught.
SOURCE_ROOTS = ("src", "src-tauri/src", "src-tauri/Cargo.toml",
                "src-tauri/tauri.conf.json", "package.json", "index.html")


def test_the_freshness_check_exists_and_is_executable():
    assert CHECK.is_file()
    assert os.access(CHECK, os.X_OK), "the launcher calls it directly"


def test_the_check_covers_every_source_the_binary_is_built_from():
    script = CHECK.read_text(encoding="utf-8")
    for path in SOURCE_ROOTS:
        assert path in script, f"{path} changes behaviour but is not checked"
    # Build OUTPUT must be excluded, or the check compares the binary to itself
    # and is stale-by-construction the moment it is rebuilt.
    assert "node_modules" in script and "target" in script


def test_the_launcher_warns_but_never_refuses_to_open():
    """A guard that turns a stale window into no window is a worse fault.

    The desktop entry runs with Terminal=false, so a refusal would be invisible.
    """
    launcher = RUN.read_text(encoding="utf-8")
    assert "check-binary-fresh.sh" in launcher, "the launch path must check"
    assert "notify-send" in launcher, "a GUI launch needs a GUI warning"
    assert launcher.rstrip().endswith('exec "$BIN"'), (
        "the launcher must still end by launching the app unconditionally")


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_the_check_actually_detects_a_source_newer_than_the_binary(tmp_path):
    """A negative control: the guard must fire, not merely exist."""
    if not BINARY.exists():
        pytest.skip("no release binary in this checkout (CI does not build one)")
    probe = DESKTOP / "src" / "__staleness_probe_test__.tsx"
    probe.write_text("// transient probe written by the test suite\n")
    try:
        result = subprocess.run(["bash", str(CHECK)], cwd=str(DESKTOP),
                                capture_output=True, text=True)
        assert result.returncode == 1, result.stdout + result.stderr
        assert "__staleness_probe_test__" in result.stderr
        assert "rebuild.sh" in result.stderr, "the failure must say what to do"
    finally:
        probe.unlink(missing_ok=True)


def test_the_built_binary_is_not_older_than_the_sources():
    """The one that would have caught the thirteen-day gap.

    Editing `src/` or `src-tauri/` and not rebuilding leaves the icon running
    yesterday's app. If this fails, run ./project-cam-desktop/rebuild.sh — the
    failure is the point, not a flake.
    """
    if not BINARY.exists():
        pytest.skip("no release binary in this checkout (CI does not build one)")
    result = subprocess.run(["bash", str(CHECK)], cwd=str(DESKTOP),
                            capture_output=True, text=True)
    assert result.returncode == 0, (
        "the desktop binary is older than the source tree — the icon would run "
        "stale behaviour:\n" + result.stderr)
