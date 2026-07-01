## Relay Git Sync

Relay Git Sync connects to your self-hosted Relay Server to sync and back up documents.
In order to connect to your Relay Server, we need to generate an API key.

The API key is scoped to your relay.md server UUID. The self-hosted Relay
Server binary uses public-key cryptography for API key generation. The setup command generates
an EdDSA public/private keypair and then uses it to sign a read-only API key.

You will need to add the generated public key to your self-hosted relay server's
relay.toml file.

The API key should be added to the environment for Git Sync so it can access your server.
The Relay Server verifies the server URL in the API key (the 'audience'), so it must match
the `url` in your relay.toml file.

### Relay server

Add this to `relay.toml`:

```toml
[[auth]]
key_id = "{key_id}"
public_key = "{public_key}"
allowed_token_types = ["prefix"]{relay_webhook_toml}
```

{webhook_note}

### Git Sync

Set these environment variables in the Git Sync deployment:

```bash
RELAY_SERVER_URL={server_url}
RELAY_SERVER_API_KEY={token}{git_sync_webhook_env}
```

{expiry_note}
