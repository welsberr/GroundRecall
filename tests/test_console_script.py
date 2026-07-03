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
    assert "claim-evaluation-export" in result.stdout
    assert "protocol-init" in result.stdout


def test_groundrecall_subcommand_help_reaches_subcommand_parser() -> None:
    executable = shutil.which("groundrecall")
    assert executable is not None

    result = subprocess.run(
        [executable, "protocol-init", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--host-id" in result.stdout
    assert "--host-role" in result.stdout
