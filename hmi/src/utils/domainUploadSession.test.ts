import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  clearDomainUploadSession,
  getDomainUploadSession,
  patchDomainUploadSession,
  resetDomainUploadSessionsForTests,
  subscribeDomainUploadSession,
} from "./domainUploadSession.ts";

beforeEach(() => {
  resetDomainUploadSessionsForTests();
});

test("keeps pending files and progress across remounts", () => {
  const file = new File(["tree"], "model_lgbm.txt", { type: "text/plain" });
  patchDomainUploadSession("Supe.Linea1.PFM", {
    pendingFiles: { artifacts_detection: [file] },
    uploadProgress: { percent: 42, current: 1, total: 2, nodeLabel: "edge" },
    saving: true,
  });

  const snap = getDomainUploadSession("Supe.Linea1.PFM");
  assert.equal(snap.saving, true);
  assert.equal(snap.uploadProgress?.percent, 42);
  assert.equal(snap.pendingFiles.artifacts_detection?.[0]?.name, "model_lgbm.txt");
});

test("notifies subscribers when the session is patched", () => {
  let ticks = 0;
  const unsub = subscribeDomainUploadSession("Supe.Linea1.Observer", () => {
    ticks += 1;
  });
  patchDomainUploadSession("Supe.Linea1.Observer", { saving: true });
  patchDomainUploadSession("Supe.Linea1.Observer", {
    uploadProgress: { percent: 10, current: 1, total: 1, nodeLabel: "n" },
  });
  assert.equal(ticks, 2);
  clearDomainUploadSession("Supe.Linea1.Observer");
  assert.equal(ticks, 3);
  assert.equal(getDomainUploadSession("Supe.Linea1.Observer").saving, false);
  unsub();
});
