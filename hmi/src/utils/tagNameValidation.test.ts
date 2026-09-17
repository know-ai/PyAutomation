import { test } from "node:test";
import assert from "node:assert/strict";
import {
  applyCreateTagNamePrefix,
  edgeTagNamePrefix,
  validateUserTagNameInput,
} from "./tagNameValidation.ts";

const SITE = "Supe";
const AREA = "Linea1";

test("edgeTagNamePrefix ends with a trailing dot", () => {
  assert.equal(edgeTagNamePrefix(SITE, AREA), "Supe.Linea1.");
  assert.equal(edgeTagNamePrefix("", AREA), "");
  assert.equal(edgeTagNamePrefix(SITE, ""), "");
});

test("applyCreateTagNamePrefix keeps the edge prefix for the configurator to complete", () => {
  assert.equal(applyCreateTagNamePrefix("", SITE, AREA), "Supe.Linea1.");
  assert.equal(applyCreateTagNamePrefix("Supe.Linea1.", SITE, AREA), "Supe.Linea1.");
  assert.equal(applyCreateTagNamePrefix("FI_01", SITE, AREA), "Supe.Linea1.FI_01");
  assert.equal(
    applyCreateTagNamePrefix("Supe.Linea1.FI_01", SITE, AREA),
    "Supe.Linea1.FI_01"
  );
});

test("applyCreateTagNamePrefix restores the prefix if the user deletes into it", () => {
  assert.equal(
    applyCreateTagNamePrefix("Supe.Linea1", SITE, AREA, "Supe.Linea1."),
    "Supe.Linea1."
  );
  assert.equal(applyCreateTagNamePrefix("", SITE, AREA, "Supe.Linea1."), "Supe.Linea1.");
});

test("applyCreateTagNamePrefix keeps a replacement letter as the base name", () => {
  assert.equal(applyCreateTagNamePrefix("S", SITE, AREA, "Supe.Linea1."), "Supe.Linea1.S");
  assert.equal(applyCreateTagNamePrefix("FI_01", SITE, AREA, "Supe.Linea1."), "Supe.Linea1.FI_01");
});

test("prefix-only name is incomplete until the user types the base", () => {
  const trailing = validateUserTagNameInput("Supe.Linea1.", SITE, AREA);
  assert.equal(trailing.ok, false);
  assert.equal(trailing.message, "incomplete");

  const noDot = validateUserTagNameInput("Supe.Linea1", SITE, AREA);
  assert.equal(noDot.ok, false);
  assert.equal(noDot.message, "incomplete");
});

test("completed prefixed name is accepted", () => {
  const result = validateUserTagNameInput("Supe.Linea1.FI_01", SITE, AREA);
  assert.equal(result.ok, true);
  assert.equal(result.qualifiedName, "Supe.Linea1.FI_01");
  assert.equal(result.baseName, "FI_01");
});

test("bare name is still qualified when the input has no prefix yet", () => {
  const result = validateUserTagNameInput("FI_01", SITE, AREA);
  assert.equal(result.ok, true);
  assert.equal(result.qualifiedName, "Supe.Linea1.FI_01");
  assert.equal(result.baseName, "FI_01");
});
