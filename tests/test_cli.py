import subprocess
import sys

from somnia import __version__


def test_cli_version():
    cmd = [sys.executable, "-m", "somnia", "--version"]
    assert subprocess.check_output(cmd).decode().strip() == __version__
