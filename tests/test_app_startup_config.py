import pytest

from app import run_server


def test_run_server_prints_setup_when_api_key_is_missing(tmp_path, capsys):
    run_server(
        "https://auth.system3.dev",
        "",
        "",
        relay_id="85a06712-af14-47bc-a859-e8106cc786e8",
        data_dir=str(tmp_path),
    )

    output = capsys.readouterr().out
    assert output.startswith("## Relay Git Sync")
    assert "RELAY_SERVER_API_KEY=" in output
    assert "WEBHOOK_SECRET=" not in output


def test_run_server_requires_relay_id_to_print_setup(tmp_path):
    with pytest.raises(ValueError, match="Relay ID is required"):
        run_server(
            "https://auth.system3.dev",
            "",
            "",
            data_dir=str(tmp_path),
        )


def test_run_server_requires_relay_id_even_with_api_key(tmp_path):
    with pytest.raises(ValueError, match="Relay ID is required"):
        run_server(
            "https://auth.system3.dev",
            "api-key",
            "",
            data_dir=str(tmp_path),
        )
