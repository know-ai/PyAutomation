import { test } from "node:test";
import assert from "node:assert/strict";
import { hasAction, hasRestFragment } from "./access.ts";

test("hasAction still gates embedded HMI views with view/use lists", () => {
  const views = { "hmi:view.machines.detailed": ["view"] };
  assert.equal(hasAction(views, "hmi:view.machines.detailed", "view"), true);
  assert.equal(hasAction(views, "hmi:view.machines.detailed", "use"), false);
});

test("canRest default use ignores GET even if that GET is true", () => {
  const rest = {
    "rest:GET /api/admin/workers": true,
    "rest:POST /api/admin/workers": false,
  };
  assert.equal(hasRestFragment(rest, "/api/admin/workers", "use"), false);
  assert.equal(hasRestFragment(rest, "/api/admin/workers", "view"), true);
});

test("canRest use is true only when the mutating REST key is allowed", () => {
  const rest = {
    "rest:GET /api/alarms": true,
    "rest:POST /api/alarms/add": true,
  };
  assert.equal(hasRestFragment(rest, "/api/alarms/add", "use"), true);
  assert.equal(hasRestFragment(rest, "/api/alarms/add", "view"), false);
});
