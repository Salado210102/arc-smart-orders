import { test } from "node:test";
import assert from "node:assert/strict";

import { ARC_MAINNET, ARC_TESTNET } from "../src/index.ts";

import type {
  Authorization,
  SignedIntent,
  TradeIntent,
} from "../src/index.ts";

type IsAssignable<A, B> = [A] extends [B] ? true : false;

type TradeIntentIsNotAuthorization = IsAssignable<TradeIntent, Authorization> extends false
  ? true
  : false;
type SignedIntentIsNotAuthorization = IsAssignable<SignedIntent, Authorization> extends false
  ? true
  : false;

const tradeIntentIsNotAuthorization: TradeIntentIsNotAuthorization = true;
const signedIntentIsNotAuthorization: SignedIntentIsNotAuthorization = true;

test("arc mainnet chain id is 5042", () => {
  assert.equal(ARC_MAINNET.chainId, 5042);
});

test("arc testnet chain id is 5042002", () => {
  assert.equal(ARC_TESTNET.chainId, 5042002);
});

test("arc native gas token uses 18 decimals", () => {
  assert.equal(ARC_MAINNET.nativeDecimals, 18);
  assert.equal(ARC_TESTNET.nativeDecimals, 18);
});

test("no websocket endpoint is invented for mainnet", () => {
  assert.equal(ARC_MAINNET.wsUrl, null);
});

test("testnet uses its own explorer host", () => {
  assert.equal(ARC_TESTNET.explorerUrl, "https://explorer.testnet.arc.io");
  assert.notEqual(ARC_TESTNET.explorerUrl, ARC_MAINNET.explorerUrl);
});

test("trade intent and authorization stay distinct types", () => {
  assert.equal(tradeIntentIsNotAuthorization, true);
  assert.equal(signedIntentIsNotAuthorization, true);
});
