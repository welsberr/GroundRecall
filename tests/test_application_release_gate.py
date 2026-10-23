from groundrecall.mcp_http import MCPHTTPApplication, MCPHTTPConfig


def test_store_configuration_does_not_enable_experimental_routes(tmp_path):
    policy = tmp_path / "policy.yaml"
    policy.write_text("schema_version: groundrecall.policy_plugins.v1\nproviders: []\n")
    app = MCPHTTPApplication(MCPHTTPConfig(policy_config=str(policy), store_dir=str(tmp_path)))
    assert app.application_api is None
