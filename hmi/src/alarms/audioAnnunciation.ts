/** Synthetic alarm tones. Same catalog Ribal uses: frequency, duration, waveform. */

export type Waveform = "sine" | "square" | "sawtooth" | "triangle" | "pulse";

export type SoundDefinition = {
  id: number;
  nameKey: string;
  frequencyHz: number;
  durationMs: number;
  waveform: Waveform;
  pulseWidthPercent?: number;
};

export type AlarmAudioProfile = {
  priority: 1 | 2 | 3 | 4;
  soundId: number;
  repeatSeconds: number;
};

export type AlarmAudioDocument = {
  muted: boolean;
  profiles: AlarmAudioProfile[];
  updatedAt?: string | null;
};

export type AudibleCue = {
  id: string;
  priority: number;
};

export const PRIORITIES = [1, 2, 3, 4] as const;
export const MIN_REPEAT_SECONDS = 2;

export const SOUND_CATALOG: SoundDefinition[] = [
  { id: 1, nameKey: "alarmAudio.soundSoftBeep440", frequencyHz: 440, durationMs: 180, waveform: "sine" },
  { id: 2, nameKey: "alarmAudio.soundClassicBeep880", frequencyHz: 880, durationMs: 200, waveform: "sine" },
  { id: 3, nameKey: "alarmAudio.soundUrgentBeep1200", frequencyHz: 1200, durationMs: 160, waveform: "sine" },
  { id: 4, nameKey: "alarmAudio.soundSquareAlert", frequencyHz: 1000, durationMs: 180, waveform: "square" },
  { id: 5, nameKey: "alarmAudio.soundSquareLow", frequencyHz: 660, durationMs: 220, waveform: "square" },
  { id: 6, nameKey: "alarmAudio.soundSawBuzz", frequencyHz: 700, durationMs: 200, waveform: "sawtooth" },
  { id: 7, nameKey: "alarmAudio.soundSawUrgent", frequencyHz: 1100, durationMs: 150, waveform: "sawtooth" },
  { id: 8, nameKey: "alarmAudio.soundTriangleChime", frequencyHz: 880, durationMs: 280, waveform: "triangle" },
  { id: 9, nameKey: "alarmAudio.soundTriangleSoft", frequencyHz: 520, durationMs: 320, waveform: "triangle" },
  { id: 10, nameKey: "alarmAudio.soundPulseShort", frequencyHz: 900, durationMs: 140, waveform: "pulse", pulseWidthPercent: 30 },
  { id: 11, nameKey: "alarmAudio.soundPulseWide", frequencyHz: 750, durationMs: 220, waveform: "pulse", pulseWidthPercent: 55 },
  { id: 12, nameKey: "alarmAudio.soundPulseUrgent", frequencyHz: 1300, durationMs: 120, waveform: "pulse", pulseWidthPercent: 25 },
];

const BY_ID = new Map(SOUND_CATALOG.map((sound) => [sound.id, sound]));

export const DEFAULT_ALARM_AUDIO: AlarmAudioDocument = {
  muted: false,
  profiles: [
    { priority: 1, soundId: 4, repeatSeconds: 2 },
    { priority: 2, soundId: 4, repeatSeconds: 5 },
    { priority: 3, soundId: 4, repeatSeconds: 10 },
    { priority: 4, soundId: 4, repeatSeconds: 30 },
  ],
};

export function alarmAudioDiffers(current: AlarmAudioDocument, saved: AlarmAudioDocument): boolean {
  if (Boolean(current.muted) !== Boolean(saved.muted)) return true;
  return PRIORITIES.some((priority) => {
    const left = current.profiles.find((row) => row.priority === priority);
    const right = saved.profiles.find((row) => row.priority === priority);
    return left?.soundId !== right?.soundId || Number(left?.repeatSeconds) !== Number(right?.repeatSeconds);
  });
}

export function soundById(soundId: number): SoundDefinition {
  return BY_ID.get(soundId) || SOUND_CATALOG[1];
}

export function intervalViolation(profiles: AlarmAudioProfile[]): string | null {
  let previous: number | null = null;
  for (const priority of PRIORITIES) {
    const row = profiles.find((item) => item.priority === priority);
    if (!row || row.repeatSeconds < MIN_REPEAT_SECONDS) {
      return "short";
    }
    if (previous != null && row.repeatSeconds <= previous) {
      return "order";
    }
    previous = row.repeatSeconds;
  }
  return null;
}

export function urgentPriority(cues: Iterable<{ priority?: number | null }>): number | null {
  let found: number | null = null;
  for (const cue of cues) {
    const priority = Number(cue.priority);
    if (!Number.isFinite(priority)) continue;
    if (found == null || priority < found) found = priority;
  }
  return found;
}

export function annunciationFor(
  cues: Iterable<{ priority?: number | null }>,
  profiles: AlarmAudioProfile[]
): { priority: number | null; soundId: number; repeatSeconds: number; count: number } {
  const list = Array.from(cues);
  const priority = urgentPriority(list);
  const row = profiles.find((item) => item.priority === priority) || DEFAULT_ALARM_AUDIO.profiles[2];
  return {
    priority,
    soundId: row.soundId,
    repeatSeconds: Math.max(MIN_REPEAT_SECONDS, row.repeatSeconds),
    count: list.length,
  };
}
