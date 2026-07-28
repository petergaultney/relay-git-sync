import json

import cli

RELAY_ID = "85a06712-af14-47bc-a859-e8106cc786e8"
OTHER_RELAY_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
RELAY_URL = "https://auth.system3.dev"
WEBHOOK_URL = "https://git-sync.example.com/webhooks"


def write_git_connectors(
    tmp_path,
    relay_id=RELAY_ID,
    relay_url=RELAY_URL,
    webhook_url=None,
):
    webhook_config = (
        f"""
[webhook]
url = "{webhook_url}"
"""
        if webhook_url
        else ""
    )
    config_file = tmp_path / "git_connectors.toml"
    config_file.write_text(
        f"""
[relay]
id = "{relay_id}"
url = "{relay_url}"
{webhook_config}

[[git_connector]]
shared_folder_id = "3667fcda-755e-472b-abea-4b4fc96873a9"
url = "https://github.com/example/repo.git"
""",
        encoding="utf-8",
    )
    return config_file


def write_relay_config(
    tmp_path,
    relay_id=RELAY_ID,
    relay_url=RELAY_URL,
    webhook_url=None,
):
    webhook_config = (
        f"""
[webhook]
url = "{webhook_url}"
"""
        if webhook_url
        else ""
    )
    config_file = tmp_path / "git_connectors.toml"
    config_file.write_text(
        f"""
[relay]
id = "{relay_id}"
url = "{relay_url}"
{webhook_config}
""",
        encoding="utf-8",
    )
    return config_file


def write_legacy_git_connectors(tmp_path, relay_ids):
    entries = []
    for index, relay_id in enumerate(relay_ids):
        entries.append(
            f"""
[[git_connector]]
shared_folder_id = "3667fcda-755e-472b-abea-4b4fc96873a9"
relay_id = "{relay_id}"
url = "https://github.com/example/repo-{index}.git"
"""
        )
    config_file = tmp_path / "git_connectors.toml"
    config_file.write_text("\n".join(entries), encoding="utf-8")
    return config_file


def test_cli_setup_outputs_relay_auth_json(tmp_path, capsys):
    exit_code = cli.main(
        [
            "--data-dir",
            str(tmp_path),
            "setup",
            "--server-url",
            "https://auth.system3.dev",
            "--relay-id",
            "relay-id",
            "--json",
        ]
    )

    assert exit_code == 0

    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"data"}
    assert payload["data"]["publicKey"]["keyId"].startswith("git-sync-")
    assert payload["data"]["token"]["serverUrl"] == "https://auth.system3.dev"
    assert payload["data"]["token"]["scope"] == "prefix:relay-id-:r"
    assert payload["data"]["token"]["expiresAt"] is None
    assert payload["data"]["token"]["env"]["RELAY_SERVER_API_KEY"]
    assert payload["data"]["webhook"] is None


def test_cli_setup_accepts_webhook_url(capsys):
    exit_code = cli.main(
        [
            "generate-auth",
            "--server-url",
            "https://auth.system3.dev",
            "--relay-id",
            "relay-id",
            "--webhook-url",
            "https://git-sync.example.com/webhooks",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["webhook"]["url"] == "https://git-sync.example.com/webhooks"


def test_cli_setup_infers_relay_id_from_git_config(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("RELAY_ID", raising=False)
    monkeypatch.delenv("RELAY_SERVER_URL", raising=False)
    write_git_connectors(tmp_path)

    exit_code = cli.main(
        [
            "--data-dir",
            str(tmp_path),
            "setup",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["token"]["relayId"] == RELAY_ID
    assert payload["data"]["token"]["serverUrl"] == RELAY_URL
    assert payload["data"]["token"]["scope"] == f"prefix:{RELAY_ID}-:r"
    assert payload["data"]["webhook"] is None


def test_cli_setup_reads_relay_table_without_connectors(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("RELAY_ID", raising=False)
    monkeypatch.delenv("RELAY_SERVER_URL", raising=False)
    write_relay_config(tmp_path)

    exit_code = cli.main(
        [
            "--data-dir",
            str(tmp_path),
            "generate-auth",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["token"]["relayId"] == RELAY_ID
    assert payload["data"]["token"]["serverUrl"] == RELAY_URL
    assert payload["data"]["webhook"] is None


def test_cli_setup_reads_webhook_url_from_git_config(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("RELAY_ID", raising=False)
    monkeypatch.delenv("RELAY_SERVER_URL", raising=False)
    write_relay_config(tmp_path, webhook_url=WEBHOOK_URL)

    exit_code = cli.main(
        [
            "--data-dir",
            str(tmp_path),
            "generate-auth",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["webhook"]["url"] == WEBHOOK_URL
    assert payload["data"]["webhook"]["env"]["WEBHOOK_SECRET"]


def test_cli_setup_prefers_relay_table_over_env(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RELAY_ID", OTHER_RELAY_ID)
    monkeypatch.setenv("RELAY_SERVER_URL", "https://env.example.test")
    write_relay_config(tmp_path)

    exit_code = cli.main(
        [
            "--data-dir",
            str(tmp_path),
            "generate-auth",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["token"]["relayId"] == RELAY_ID
    assert payload["data"]["token"]["serverUrl"] == RELAY_URL
    assert payload["data"]["webhook"] is None


def test_cli_setup_infers_relay_id_from_config_flag(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("RELAY_ID", raising=False)
    monkeypatch.delenv("RELAY_SERVER_URL", raising=False)
    config_file = write_git_connectors(tmp_path)

    exit_code = cli.main(
        [
            "setup",
            "-c",
            str(config_file),
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["token"]["relayId"] == RELAY_ID
    assert payload["data"]["token"]["serverUrl"] == RELAY_URL
    assert payload["data"]["webhook"] is None


def test_cli_generate_auth_alias_infers_relay_id_from_git_config(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("RELAY_ID", raising=False)
    monkeypatch.delenv("RELAY_SERVER_URL", raising=False)
    write_git_connectors(tmp_path)

    exit_code = cli.main(
        [
            "--data-dir",
            str(tmp_path),
            "generate-auth",
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["token"]["relayId"] == RELAY_ID


def test_cli_setup_uses_relay_id_arg_before_git_config(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("RELAY_ID", raising=False)
    monkeypatch.delenv("RELAY_SERVER_URL", raising=False)
    write_git_connectors(tmp_path, relay_id=OTHER_RELAY_ID)

    exit_code = cli.main(
        [
            "--data-dir",
            str(tmp_path),
            "setup",
            "--relay-id",
            RELAY_ID,
            "--json",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["token"]["relayId"] == RELAY_ID


def test_cli_setup_requires_arg_when_git_config_has_multiple_relays(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("RELAY_ID", raising=False)
    monkeypatch.delenv("RELAY_SERVER_URL", raising=False)
    write_legacy_git_connectors(tmp_path, [RELAY_ID, OTHER_RELAY_ID])

    exit_code = cli.main(
        [
            "--data-dir",
            str(tmp_path),
            "setup",
            "--server-url",
            "https://auth.system3.dev",
        ]
    )

    assert exit_code == 1
    assert "Multiple relay IDs found" in capsys.readouterr().out


def test_cli_inspect_token_uses_env_api_key(monkeypatch, capsys):
    setup_exit_code = cli.main(
        [
            "setup",
            "--server-url",
            "https://auth.system3.dev",
            "--relay-id",
            "relay-id",
            "--json",
        ]
    )
    assert setup_exit_code == 0
    setup_payload = json.loads(capsys.readouterr().out)

    monkeypatch.setenv("RELAY_SERVER_API_KEY", setup_payload["data"]["token"]["value"])

    inspect_exit_code = cli.main(["inspect-token", "--json"])

    assert inspect_exit_code == 0
    inspect_payload = json.loads(capsys.readouterr().out)
    assert inspect_payload["data"]["token"]["keyId"] == setup_payload["data"]["publicKey"]["keyId"]
    assert inspect_payload["data"]["token"]["serverUrl"] == "https://auth.system3.dev"
    assert inspect_payload["data"]["token"]["scope"] == "prefix:relay-id-:r"


def test_cli_sync_prints_setup_when_api_key_is_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("RELAY_SERVER_API_KEY", raising=False)
    monkeypatch.delenv("RELAY_ID", raising=False)
    monkeypatch.delenv("RELAY_SERVER_URL", raising=False)
    write_git_connectors(tmp_path)

    exit_code = cli.main(
        [
            "--data-dir",
            str(tmp_path),
            "sync",
        ]
    )

    assert exit_code == 1
    output = capsys.readouterr().out
    assert output.startswith("## Relay Git Sync")
    assert "RELAY_SERVER_API_KEY=" in output
    assert "WEBHOOK_SECRET=" not in output
