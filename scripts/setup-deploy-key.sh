#!/usr/bin/env bash
set -euo pipefail

SPIDER_REPO="VoidNxSEC/spider-nix"
CONSUMER_REPO="VoidNxSEC/securellm-mcp"
KEY_FILE="/tmp/spider-nix-deploy"
KEY_TITLE="securellm-mcp-ci"

cleanup() { rm -f "$KEY_FILE" "$KEY_FILE.pub"; }
trap cleanup EXIT

echo "==> Gerando deploy key ed25519..."
ssh-keygen -t ed25519 -C "$KEY_TITLE" -f "$KEY_FILE" -N "" -q

echo "==> Adicionando public key em $SPIDER_REPO (read-only)..."
gh api repos/$SPIDER_REPO/keys \
  --method POST \
  -f title="$KEY_TITLE" \
  -f key="$(cat "$KEY_FILE.pub")" \
  -F read_only=true \
  --jq '"Deploy key criada: id=\(.id) title=\(.title)"'

echo "==> Adicionando private key como secret SPIDER_NIX_DEPLOY_KEY em $CONSUMER_REPO..."
gh secret set SPIDER_NIX_DEPLOY_KEY \
  --repo "$CONSUMER_REPO" \
  --body "$(cat "$KEY_FILE")"

echo ""
echo "Pronto. Pode trancar o spider-nix agora."
