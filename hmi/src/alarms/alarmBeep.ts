import { soundById, type SoundDefinition } from "./audioAnnunciation";

/** Plays one synthetic beep. The browser may stay silent until a user gesture. */
export function playAlarmBeep(soundId: number, context?: AudioContext | null): void {
  const audio = context || new AudioContext();
  const sound = soundById(soundId);
  const osc = audio.createOscillator();
  const gain = audio.createGain();
  osc.type = sound.waveform === "pulse" ? "square" : sound.waveform;
  osc.frequency.value = sound.frequencyHz;
  const start = audio.currentTime;
  const end = start + sound.durationMs / 1000;
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(0.2, start + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, end);
  osc.connect(gain);
  gain.connect(audio.destination);
  osc.start(start);
  osc.stop(end);
  void audio.resume();
}

export type AnnunciationSync = {
  count: number;
  repeatSeconds: number;
  soundId: number;
  muted: boolean;
};

/**
 * Repeats the most urgent unacknowledged tone.
 * A new unacknowledged alarm plays immediately. Silence stops the timer.
 */
export class AlarmAnnunciator {
  private timer: ReturnType<typeof setInterval> | null = null;
  private count = -1;
  private repeatSeconds = 10;
  private soundId = 2;
  private muted = false;
  private context: AudioContext | null = null;

  sync(next: AnnunciationSync): void {
    const previous = this.count;
    const previousSound = this.soundId;
    const previousInterval = this.repeatSeconds;
    this.count = next.count;
    this.repeatSeconds = Math.max(2, next.repeatSeconds);
    this.soundId = next.soundId;
    this.muted = next.muted;
    if (next.count === 0 || next.muted) {
      this.stop();
      return;
    }
    const changed = this.timer == null || previousSound !== this.soundId || previousInterval !== this.repeatSeconds;
    if (changed) this.restart();
    if (next.count > previous) this.play();
  }

  preview(soundId: number): void {
    this.play(soundId, true);
  }

  stop(): void {
    if (this.timer != null) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  private restart(): void {
    this.stop();
    this.timer = setInterval(() => this.play(), this.repeatSeconds * 1000);
  }

  private play(soundId = this.soundId, force = false): void {
    if (!force && this.muted) return;
    try {
      if (!this.context) this.context = new AudioContext();
      playAlarmBeep(soundId, this.context);
    } catch {
      /* autoplay blocked until the operator interacts with the page */
    }
  }
}

export function soundLabel(sound: SoundDefinition, name: string): string {
  return `${name} · ${sound.frequencyHz} Hz`;
}
