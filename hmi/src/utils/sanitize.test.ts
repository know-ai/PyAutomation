import { test } from "node:test";
import assert from "node:assert/strict";
import { filterChartsToCatalog, sanitizeCard } from "./sanitize.ts";

const base = {
  id: "c1",
  title: "Chart",
  tagNames: ["FI_01", "GONE"],
  timeSpanMinutes: 2,
  x: 0,
  y: 0,
  w: 24,
  h: 15,
};

test("sanitizeCard drops showThresholds", () => {
  const result = sanitizeCard({ ...base, showThresholds: true });
  assert.equal("showThresholds" in result, false);
  assert.deepEqual(result.tagNames, ["FI_01", "GONE"]);
});

test("sanitizeCard filters orphan tag names when catalog is provided", () => {
  const result = sanitizeCard(base, new Set(["FI_01"]));
  assert.deepEqual(result.tagNames, ["FI_01"]);
});

test("empty catalog does not strip tags", () => {
  const result = sanitizeCard(base, new Set());
  assert.deepEqual(result.tagNames, ["FI_01", "GONE"]);
});

test("filterChartsToCatalog returns the same array when nothing changes", () => {
  const charts = [{ ...base, tagNames: ["FI_01"] }];
  const next = filterChartsToCatalog(charts, new Set(["FI_01"]));
  assert.equal(next, charts);
});

test("filterChartsToCatalog strips orphans and thresholds", () => {
  const charts = [{ ...base, showThresholds: false }];
  const next = filterChartsToCatalog(charts, new Set(["FI_01"]));
  assert.notEqual(next, charts);
  assert.deepEqual(next[0].tagNames, ["FI_01"]);
  assert.equal("showThresholds" in next[0], false);
});
