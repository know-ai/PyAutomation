import { test } from "node:test";
import assert from "node:assert/strict";
import { TAG_PICKER_ITEM_HEIGHT } from "./tagPicker.ts";

test("VirtualList itemHeight is a numeric constant of 48", () => {
  assert.equal(typeof TAG_PICKER_ITEM_HEIGHT, "number");
  assert.equal(TAG_PICKER_ITEM_HEIGHT, 48);
});
