#!/usr/bin/env bash
# Fund the Arc MAINNET keeper hot wallet (B) with native USDC for gas.
#
# On Arc, gas is paid in the NATIVE USDC (18-decimal accounting). The keeper (B) must hold a
# small native-USDC balance so it can broadcast fills once DRY=0 is enabled.
#
#   bash ops/fund-keeper.sh                 # defaults below
#   AMOUNT=1ether bash ops/fund-keeper.sh   # override the amount
#
# Env: RPC (default mainnet), KEEPER (default B), AMOUNT (default 2ether), KEY_FILE (signer A).
# Signer A must hold mainnet USDC (it pays the transfer).
set -euo pipefail

RPC="${RPC:-https://rpc.mainnet.arc.io}"
KEEPER="${KEEPER:-0x327fF705C1De5Ffd071bDF7E43069398507E50bC}"
AMOUNT="${AMOUNT:-2ether}"                        # native USDC (18 dec) == gas
KEY_FILE="${KEY_FILE:-/root/.arc-deployer.json}"  # signer A (funding source)

command -v cast >/dev/null || { echo "✗ cast (foundry) not found in PATH"; exit 1; }
command -v jq   >/dev/null || { echo "✗ jq required (apt-get install -y jq)"; exit 1; }

echo "== Fund Arc keeper (mainnet) =="
echo "RPC:    $RPC"
echo "keeper: $KEEPER"
echo "amount: $AMOUNT  (native USDC, 18 dec)"

echo "→ gas balance before:"
cast balance "$KEEPER" --rpc-url "$RPC"

PK="$(jq -r '.privateKey // .private_key' "$KEY_FILE")"
[ -n "$PK" ] && [ "$PK" != "null" ] || { echo "✗ no privateKey in $KEY_FILE"; exit 1; }

echo "→ sending $AMOUNT to keeper…"
cast send "$KEEPER" --value "$AMOUNT" --private-key "$PK" --rpc-url "$RPC"

echo "→ gas balance after:"
cast balance "$KEEPER" --rpc-url "$RPC"
echo "✅ keeper funded (native USDC)"
