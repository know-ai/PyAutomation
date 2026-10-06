import assert from "node:assert/strict";
import test from "node:test";
import { clampDialogPosition } from "./src/components/draggableModals.ts";

test("keeps the dialog title on screen", () => {
  assert.deepEqual(clampDialogPosition(400, -80, -20, 1000, 800), { x: -80, y: 0 });
  assert.deepEqual(clampDialogPosition(400, 900, 900, 1000, 800), { x: 900, y: 752 });
});

test("lets a wide dialog slide until a strip stays visible", () => {
  assert.deepEqual(clampDialogPosition(1400, -2000, 10, 1000, 800), { x: -1352, y: 10 });
});
