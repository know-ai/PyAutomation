import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useAppSelector } from "../hooks/useAppSelector";
import { AlarmAnnunciator } from "../alarms/alarmBeep";
import {
  annunciationFor,
  DEFAULT_ALARM_AUDIO,
  type AlarmAudioDocument,
  type AlarmAudioProfile,
} from "../alarms/audioAnnunciation";
import { getAlarmAudio } from "../services/alarmAudio";

type AlarmAudioContextValue = {
  profile: AlarmAudioDocument;
  savedProfile: AlarmAudioDocument;
  setProfile: (profile: AlarmAudioDocument) => void;
  commitProfile: (profile: AlarmAudioDocument) => void;
  sessionMuted: boolean;
  toggleSessionMute: () => void;
  preview: (soundId: number) => void;
};

const AlarmAudioContext = createContext<AlarmAudioContextValue | null>(null);

export function useAlarmAudio(): AlarmAudioContextValue {
  const value = useContext(AlarmAudioContext);
  if (!value) throw new Error("useAlarmAudio requires AlarmAudioProvider");
  return value;
}

export function AlarmAudioProvider({ children }: { children: ReactNode }) {
  const audible = useAppSelector((state) => state.alarms.audible);
  const [profile, setProfile] = useState<AlarmAudioDocument>(DEFAULT_ALARM_AUDIO);
  const [savedProfile, setSavedProfile] = useState<AlarmAudioDocument>(DEFAULT_ALARM_AUDIO);
  const [sessionMuted, setSessionMuted] = useState(false);
  const player = useRef(new AlarmAnnunciator());

  useEffect(() => {
    let cancelled = false;
    void getAlarmAudio().then((document) => {
      if (!cancelled) {
        setProfile(document);
        setSavedProfile(document);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const cues = Object.entries(audible).map(([id, priority]) => ({ id, priority }));
    const cue = annunciationFor(cues, profile.profiles as AlarmAudioProfile[]);
    player.current.sync({
      count: cue.count,
      repeatSeconds: cue.repeatSeconds,
      soundId: cue.soundId,
      muted: sessionMuted || profile.muted,
    });
  }, [audible, profile, sessionMuted]);

  useEffect(() => () => player.current.stop(), []);

  const value = useMemo<AlarmAudioContextValue>(
    () => ({
      profile,
      savedProfile,
      setProfile,
      commitProfile: (next: AlarmAudioDocument) => {
        setProfile(next);
        setSavedProfile(next);
      },
      sessionMuted,
      toggleSessionMute: () => setSessionMuted((current) => !current),
      preview: (soundId: number) => player.current.preview(soundId),
    }),
    [profile, savedProfile, sessionMuted]
  );

  return <AlarmAudioContext.Provider value={value}>{children}</AlarmAudioContext.Provider>;
}
