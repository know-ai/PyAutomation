import assert from "node:assert/strict";
import test from "node:test";
import {
  DEFAULT_ALARM_AUDIO,
  SOUND_CATALOG,
  alarmAudioDiffers,
  annunciationFor,
  intervalViolation,
  urgentPriority,
} from "./src/alarms/audioAnnunciation.ts";

test("catalog has the twelve Ribal tones", () => {
  assert.equal(SOUND_CATALOG.length, 12);
  assert.equal(SOUND_CATALOG[11].frequencyHz, 1300);
});

test("default intervals grow as urgency drops", () => {
  assert.equal(intervalViolation(DEFAULT_ALARM_AUDIO.profiles), null);
  assert.deepEqual(
    DEFAULT_ALARM_AUDIO.profiles.map((row) => row.soundId),
    [4, 4, 4, 4]
  );
});

test("save stays idle until a tone or the mute flag changes", () => {
  assert.equal(alarmAudioDiffers(DEFAULT_ALARM_AUDIO, DEFAULT_ALARM_AUDIO), false);
  const next = {
    ...DEFAULT_ALARM_AUDIO,
    profiles: DEFAULT_ALARM_AUDIO.profiles.map((row) => ({ ...row })),
  };
  next.profiles[0].soundId = 5;
  assert.equal(alarmAudioDiffers(next, DEFAULT_ALARM_AUDIO), true);
});

test("a faster low priority is rejected", () => {
  const profiles = DEFAULT_ALARM_AUDIO.profiles.map((row) => ({ ...row }));
  profiles[3].repeatSeconds = 2;
  assert.equal(intervalViolation(profiles), "order");
});

test("the most urgent unacknowledged alarm chooses the beep", () => {
  const cue = annunciationFor(
    [{ priority: 4 }, { priority: 1 }],
    DEFAULT_ALARM_AUDIO.profiles
  );
  assert.equal(urgentPriority([{ priority: 4 }, { priority: 1 }]), 1);
  assert.equal(cue.soundId, 4);
  assert.equal(cue.repeatSeconds, 2);
  assert.equal(cue.count, 2);
});
