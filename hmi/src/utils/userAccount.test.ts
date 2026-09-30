import { test } from "node:test";
import assert from "node:assert/strict";
import { accountIsEnabled, actorMaySetUserEnabled } from "./userAccount.ts";

test("only integrator and administrator may toggle accounts", () => {
  assert.equal(actorMaySetUserEnabled("integrator"), true);
  assert.equal(actorMaySetUserEnabled("ADMIN"), true);
  assert.equal(actorMaySetUserEnabled("Administrator"), true);
  assert.equal(actorMaySetUserEnabled("sudo"), false);
  assert.equal(actorMaySetUserEnabled("supervisor"), false);
  assert.equal(actorMaySetUserEnabled("operator"), false);
  assert.equal(actorMaySetUserEnabled(undefined), false);
});

test("missing enabled flag means the account is active", () => {
  assert.equal(accountIsEnabled(undefined), true);
  assert.equal(accountIsEnabled(true), true);
  assert.equal(accountIsEnabled(false), false);
});
