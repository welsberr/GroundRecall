from groundrecall.context_cli import build_parser


def test_context_cli_exposes_load_advise_and_checkpoint():
    assert build_parser().parse_args(["load", "package"]).action == "load"
    assert build_parser().parse_args(["advise", "--observation", "a", "--coverage", "b"]).action == "advise"
    assert build_parser().parse_args(["checkpoint", "--session-id", "s", "--objective", "o", "--out", "x"]).action == "checkpoint"
