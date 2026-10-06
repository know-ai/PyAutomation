import api from "./api";
import { DEFAULT_ALARM_AUDIO, type AlarmAudioDocument } from "../alarms/audioAnnunciation";

export async function getAlarmAudio(): Promise<AlarmAudioDocument> {
  try {
    const { data } = await api.get("/settings/alarm-audio");
    if (!data || !Array.isArray(data.profiles)) return DEFAULT_ALARM_AUDIO;
    return data as AlarmAudioDocument;
  } catch {
    return DEFAULT_ALARM_AUDIO;
  }
}

export async function putAlarmAudio(document: AlarmAudioDocument): Promise<AlarmAudioDocument> {
  const { data } = await api.put("/settings/alarm-audio", {
    muted: document.muted,
    profiles: document.profiles,
  });
  return data as AlarmAudioDocument;
}
