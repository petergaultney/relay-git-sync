#!/bin/bash

# Get SSH key from environment (injected by secrets manager)
if [ -z "$SSH_PRIVATE_KEY" ]; then
    echo "SSH_PRIVATE_KEY environment variable not set"
    exit 1
fi

# Start ssh-agent
eval $(ssh-agent -s)

# Add key from environment variable
echo "$SSH_PRIVATE_KEY" | ssh-add -

# Export agent info to a file for other processes
echo "export SSH_AUTH_SOCK=$SSH_AUTH_SOCK" > /tmp/ssh-agent.env
echo "export SSH_AGENT_PID=$SSH_AGENT_PID" >> /tmp/ssh-agent.env

# SSH host keys are managed by the app (git_connectors.toml known_hosts plus
# keys fetched from hosted providers) with strict host key checking. Do not
# ssh-keyscan here: it would trust whatever host answers first.

echo "SSH agent started with PID $SSH_AGENT_PID"

eval uv run app.py
