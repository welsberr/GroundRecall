from pathlib import Path


ROOT = Path(__file__).parents[1]
UNIT = ROOT / "deploy" / "systemd" / "groundrecall-mcp-http.service"
LOGROTATE = ROOT / "deploy" / "logrotate" / "groundrecall-mcp-http"


def test_systemd_template_is_loopback_only_and_hardened():
    text = UNIT.read_text(encoding="utf-8")
    assert "--host 127.0.0.1" in text
    assert "0.0.0.0" not in text
    for directive in (
        "User=groundrecall",
        "NoNewPrivileges=yes",
        "ProtectSystem=strict",
        "PrivateTmp=yes",
        "CapabilityBoundingSet=",
        "Restart=on-failure",
        "StartLimitBurst=5",
        "ReadWritePaths=/var/lib/groundrecall /var/log/groundrecall",
    ):
        assert directive in text


def test_systemd_template_keeps_policy_and_identity_server_owned():
    text = UNIT.read_text(encoding="utf-8")
    assert "--policy-config /etc/groundrecall/mcp-policy.yaml" in text
    assert "--identity-file /etc/groundrecall/mcp-identities.json" in text
    assert "--audit-log-path /var/log/groundrecall/mcp-access.jsonl" in text


def test_logrotate_template_is_bounded_and_uses_safe_rename_rotation():
    text = LOGROTATE.read_text(encoding="utf-8")
    for directive in (
        "/var/log/groundrecall/mcp-access.jsonl",
        "daily",
        "rotate 14",
        "maxsize 50M",
        "missingok",
        "notifempty",
        "compress",
        "delaycompress",
        "dateext",
        "create 0640 groundrecall groundrecall",
    ):
        assert directive in text
    assert "copytruncate" not in text
    assert "bearer" not in text.lower()


def test_logrotate_template_has_operator_controlled_atomic_manifest_hook():
    text = LOGROTATE.read_text(encoding="utf-8")
    assert "manifest_bin=/opt/groundrecall/.venv/bin/groundrecall-mcp-audit-manifest" in text
    assert "postrotate" in text and "endscript" in text
    assert "--output /var/log/groundrecall/mcp-access.manifest.json" in text
    assert "logger -t groundrecall-mcp-audit" in text
    assert "manifest generation failed after log rotation" in text
    assert "manifest command not found" in text
    # The hook delegates atomic output to the manifest utility and never emits
    # audit records to the logrotate shell output.
    assert ">/dev/null" in text
