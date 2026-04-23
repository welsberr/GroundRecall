import shutil
import subprocess


def test_groundrecall_console_script_help() -> None:
    executable = shutil.which("groundrecall")
    assert executable is not None

    result = subprocess.run(
        [executable, "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "GroundRecall command-line tools" in result.stdout
