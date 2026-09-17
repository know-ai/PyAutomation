import { test } from "node:test";
import assert from "node:assert/strict";
import { firstUnselectedIndex, sortTagsWithSelectedFirst } from "./tagSort.ts";

test("preserves insertion order for selected", () => {
  const tags = [{ name: "A" }, { name: "B" }, { name: "C" }];
  const result = sortTagsWithSelectedFirst(tags, ["C", "A"]);
  assert.deepEqual(
    result.map((tag) => tag.name),
    ["C", "A", "B"]
  );
});

test("unselected are alphabetical after selected", () => {
  const tags = [{ name: "PI_03" }, { name: "FI_01" }, { name: "TI_05" }, { name: "AI_02" }];
  const result = sortTagsWithSelectedFirst(tags, ["TI_05", "FI_01", "PI_03"]);
  assert.deepEqual(
    result.map((tag) => tag.name),
    ["TI_05", "FI_01", "PI_03", "AI_02"]
  );
});

test("deselecting moves a tag back to the alphabetical group", () => {
  const tags = [{ name: "B" }, { name: "A" }, { name: "C" }];
  const afterSelect = sortTagsWithSelectedFirst(tags, ["C", "A"]);
  assert.deepEqual(
    afterSelect.map((tag) => tag.name),
    ["C", "A", "B"]
  );
  const afterDeselect = sortTagsWithSelectedFirst(tags, ["C"]);
  assert.deepEqual(
    afterDeselect.map((tag) => tag.name),
    ["C", "A", "B"]
  );
});

test("filter is applied by the caller; selected and unselected both remain", () => {
  const tags = [{ name: "FI_01" }, { name: "FI_02" }, { name: "PI_01" }];
  const filtered = tags.filter((tag) => tag.name.toLowerCase().includes("fi"));
  const result = sortTagsWithSelectedFirst(filtered, ["FI_02"]);
  assert.deepEqual(
    result.map((tag) => tag.name),
    ["FI_02", "FI_01"]
  );
});

test("localeCompare is case-insensitive", () => {
  const tags = [{ name: "bTag" }, { name: "ATag" }, { name: "ctag" }];
  const result = sortTagsWithSelectedFirst(tags, []);
  assert.deepEqual(
    result.map((tag) => tag.name),
    ["ATag", "bTag", "ctag"]
  );
});

test("firstUnselectedIndex points at the alphabetical group", () => {
  const tags = [{ name: "C" }, { name: "A" }, { name: "B" }];
  const sorted = sortTagsWithSelectedFirst(tags, ["C"]);
  assert.equal(firstUnselectedIndex(sorted, ["C"]), 1);
});
