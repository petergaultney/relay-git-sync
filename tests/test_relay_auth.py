import json
import re

import cbor2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from relay_auth import (
    COSE_ALG_EDDSA,
    COSE_HEADER_ALG,
    COSE_HEADER_KEY_ID,
    COSE_SIGN1_TAG,
    CWT_CLAIM_AUDIENCE,
    CWT_CLAIM_EXPIRATION,
    CWT_CLAIM_ISSUED_AT,
    CWT_CLAIM_ISSUER,
    CWT_CLAIM_SCOPE,
    CWT_TAG,
    b64url_decode,
    generate_setup,
    inspect_token,
    key_id_for_public_key,
    print_setup,
    relay_prefix,
    relay_toml_snippet,
    render_setup_markdown,
    setup_as_json,
    timestamp_text,
    token_info_as_json,
)


def decode_generated_token(token: str):
    cwt = cbor2.loads(b64url_decode(token))
    assert cwt.tag == CWT_TAG
    cose = cwt.value
    assert cose.tag == COSE_SIGN1_TAG
    protected, unprotected, payload, signature = cose.value
    return protected, unprotected, payload, signature


def test_relay_prefix_adds_separator():
    assert relay_prefix("85a06712-af14-47bc-a859-e8106cc786e8") == (
        "85a06712-af14-47bc-a859-e8106cc786e8-"
    )
    assert relay_prefix("relay-") == "relay-"


def test_setup_outputs_keypair_and_relay_config_values():
    setup = generate_setup(
        server_url="https://auth.system3.dev",
        relay_id="relay-id",
        expires_days=7,
        webhook_url="https://git-sync.example.com/webhooks",
        webhook_secret="webhook-secret",
        now=1_700_000_000,
    )

    assert len(b64url_decode(setup.keypair.private_key)) == 32
    assert len(b64url_decode(setup.keypair.public_key)) == 32
    assert setup.keypair.key_id == key_id_for_public_key(setup.keypair.public_key)
    assert setup.keypair.key_id.startswith("git-sync-")
    assert len(setup.keypair.key_id) == len("git-sync-") + 8

    snippet = relay_toml_snippet(setup.keypair)
    assert f'key_id = "{setup.keypair.key_id}"' in snippet
    assert f'public_key = "{setup.keypair.public_key}"' in snippet
    assert 'allowed_token_types = ["prefix"]' in snippet
    assert setup.webhook.url == "https://git-sync.example.com/webhooks"
    assert setup.webhook.secret == "webhook-secret"
    assert setup.webhook.prefix == "relay-id-"


def test_setup_token_is_read_only_relay_prefix_token_with_expiry():
    setup = generate_setup(
        server_url="https://auth.system3.dev",
        relay_id="relay-id",
        expires_days=7,
        now=1_700_000_000,
    )

    assert setup.token.scope == "prefix:relay-id-:r"
    assert setup.token.expires_at == 1_700_000_000 + 7 * 24 * 60 * 60
    assert "=" not in setup.token.value

    protected, unprotected, payload, signature = decode_generated_token(setup.token.value)
    assert unprotected == {}
    assert len(signature) == 64

    protected_header = cbor2.loads(protected)
    assert protected_header == {
        COSE_HEADER_ALG: COSE_ALG_EDDSA,
        COSE_HEADER_KEY_ID: setup.keypair.key_id.encode("utf-8"),
    }

    claims = cbor2.loads(payload)
    assert claims[CWT_CLAIM_ISSUER] == "relay-server"
    assert claims[CWT_CLAIM_AUDIENCE] == "https://auth.system3.dev"
    assert claims[CWT_CLAIM_EXPIRATION] == setup.token.expires_at
    assert claims[CWT_CLAIM_ISSUED_AT] == 1_700_000_000
    assert claims[CWT_CLAIM_SCOPE] == "prefix:relay-id-:r"


def test_generated_signature_verifies_with_public_key():
    setup = generate_setup(
        server_url="https://auth.system3.dev",
        relay_id="relay-id",
        expires_days=7,
        now=1_700_000_000,
    )

    protected, _, payload, signature = decode_generated_token(setup.token.value)
    signature_payload = cbor2.dumps(["Signature1", protected, b"", payload])
    public_key = Ed25519PublicKey.from_public_bytes(b64url_decode(setup.keypair.public_key))

    public_key.verify(signature, signature_payload)


def test_json_output_wraps_public_key_and_token_under_data():
    setup = generate_setup(
        server_url="https://auth.system3.dev",
        relay_id="relay-id",
        expires_days=7,
        webhook_url="https://git-sync.example.com/webhooks",
        webhook_secret="webhook-secret",
        now=1_700_000_000,
    )

    payload = json.loads(setup_as_json(setup))

    assert set(payload) == {"data"}
    assert payload["data"]["publicKey"]["keyId"] == setup.keypair.key_id
    assert payload["data"]["publicKey"]["value"] == setup.keypair.public_key
    assert "relayToml" not in payload["data"]["publicKey"]
    assert "privateKey" not in payload["data"]
    assert payload["data"]["token"]["value"] == setup.token.value
    assert payload["data"]["token"]["serverUrl"] == "https://auth.system3.dev"
    assert "audience" not in payload["data"]["token"]
    assert payload["data"]["token"]["env"]["RELAY_SERVER_API_KEY"] == setup.token.value
    assert payload["data"]["webhook"]["url"] == "https://git-sync.example.com/webhooks"
    assert payload["data"]["webhook"]["prefix"] == "relay-id-"
    assert payload["data"]["webhook"]["secret"] == "webhook-secret"
    assert payload["data"]["webhook"]["env"]["WEBHOOK_SECRET"] == "webhook-secret"


def test_setup_markdown_template_hides_private_key_and_includes_commands():
    setup = generate_setup(
        server_url="https://auth.system3.dev",
        relay_id="relay-id",
        expires_days=7,
        webhook_url="https://git-sync.example.com/webhooks",
        webhook_secret="webhook-secret",
        now=1_700_000_000,
    )

    output = render_setup_markdown(setup)

    assert setup.keypair.private_key not in output
    assert "private_key" not in output
    assert "RELAY_SERVER_API_KEY=" in output
    assert "WEBHOOK_SECRET=webhook-secret" in output
    assert 'public_key = "' in output
    assert f'key_id = "{setup.keypair.key_id}"' in output
    assert "[[webhooks]]" in output
    assert 'prefix = "relay-id-"' in output
    assert 'url = "https://git-sync.example.com/webhooks"' in output
    assert 'auth_token = "webhook-secret"' in output
    assert output.startswith("## Relay Git Sync")
    assert "In order to connect to your Relay Server" in output
    assert "scoped to your relay.md server UUID" in output
    assert "public-key cryptography" in output
    assert "### Decoded API key" not in output
    assert "Your API key expires at `2023-11-21T22:13:20Z`." in output
    assert setup.token.value in output


def test_human_output_uses_setup_template(capsys):
    setup = generate_setup(
        server_url="https://auth.system3.dev",
        relay_id="relay-id",
        expires_days=7,
        now=1_700_000_000,
    )

    print_setup(setup)
    output = capsys.readouterr().out

    assert output == render_setup_markdown(setup)


def test_tty_setup_code_blocks_use_erase_line_background(monkeypatch, capsys):
    setup = generate_setup(
        server_url="https://auth.system3.dev",
        relay_id="relay-id",
        expires_days=None,
        now=1_700_000_000,
    )
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    print_setup(setup)
    output = capsys.readouterr().out

    assert "\x1b[K" in output
    ansi_pattern = re.compile(r"\x1b\[[0-9;]*m")
    for line in output.splitlines():
        if "\x1b[K" not in line:
            continue
        before_erase = line.split("\x1b[K", 1)[0]
        assert not ansi_pattern.sub("", before_erase).endswith(" ")


def test_inspect_token_returns_human_readable_claims():
    setup = generate_setup(
        server_url="https://auth.system3.dev",
        relay_id="relay-id",
        expires_days=7,
        now=1_700_000_000,
    )

    info = inspect_token(setup.token.value)

    assert info.key_id == setup.keypair.key_id
    assert info.issuer == "relay-server"
    assert info.server_url == "https://auth.system3.dev"
    assert info.scope == "prefix:relay-id-:r"
    assert info.issued_at == 1_700_000_000
    assert info.expires_at == 1_700_000_000 + 7 * 24 * 60 * 60
    assert timestamp_text(info.expires_at) == "2023-11-21T22:13:20Z"


def test_inspect_json_wraps_token_info_under_data():
    setup = generate_setup(
        server_url="https://auth.system3.dev",
        relay_id="relay-id",
        expires_days=7,
        now=1_700_000_000,
    )
    info = inspect_token(setup.token.value)

    payload = json.loads(token_info_as_json(info))

    assert set(payload) == {"data"}
    assert payload["data"]["token"]["keyId"] == setup.keypair.key_id
    assert payload["data"]["token"]["serverUrl"] == "https://auth.system3.dev"
    assert "audience" not in payload["data"]["token"]
    assert payload["data"]["token"]["scope"] == "prefix:relay-id-:r"
    assert payload["data"]["token"]["expiresAt"] == setup.token.expires_at
    assert payload["data"]["token"]["expiresAtIso"] == "2023-11-21T22:13:20Z"


def test_setup_without_expires_days_has_no_expiration_claim_or_note():
    setup = generate_setup(
        server_url="https://auth.system3.dev",
        relay_id="relay-id",
        expires_days=None,
        now=1_700_000_000,
    )

    assert setup.token.expires_at is None

    _, _, payload, _ = decode_generated_token(setup.token.value)
    claims = cbor2.loads(payload)
    assert CWT_CLAIM_EXPIRATION not in claims

    output = render_setup_markdown(setup)
    assert "Your API key expires" not in output

    json_payload = json.loads(setup_as_json(setup))
    assert json_payload["data"]["token"]["expiresAt"] is None
