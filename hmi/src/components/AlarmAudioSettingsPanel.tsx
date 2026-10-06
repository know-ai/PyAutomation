import { useState } from "react";
import { SettingsChapter } from "./SettingsChapter";
import { Button } from "./Button";
import { useTranslation } from "../hooks/useTranslation";
import { useAlarmAudio } from "./AlarmAudioProvider";
import { putAlarmAudio } from "../services/alarmAudio";
import { showToast } from "../utils/toast";
import {
  PRIORITIES,
  SOUND_CATALOG,
  alarmAudioDiffers,
  intervalViolation,
  soundById,
  type AlarmAudioProfile,
} from "../alarms/audioAnnunciation";

type AlarmAudioSettingsPanelProps = {
  canMutate: boolean;
};

export function AlarmAudioSettingsPanel({ canMutate }: AlarmAudioSettingsPanelProps) {
  const { t } = useTranslation();
  const { profile, savedProfile, setProfile, commitProfile, preview } = useAlarmAudio();
  const [saving, setSaving] = useState(false);
  const violation = intervalViolation(profile.profiles);
  const dirty = alarmAudioDiffers(profile, savedProfile);

  const updateRow = (priority: number, patch: Partial<AlarmAudioProfile>) => {
    setProfile({
      ...profile,
      profiles: profile.profiles.map((row) =>
        row.priority === priority ? { ...row, ...patch } : row
      ) as AlarmAudioProfile[],
    });
  };

  const save = async () => {
    if (!canMutate || saving || violation || !dirty) return;
    setSaving(true);
    try {
      const saved = await putAlarmAudio(profile);
      commitProfile(saved);
      showToast(t("alarmAudio.saved"), "success");
    } catch (error: unknown) {
      const message = (error as { response?: { data?: { message?: string } } })?.response?.data?.message;
      showToast(message || t("alarmAudio.saveError"), "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SettingsChapter
      id="settings-alarm-audio"
      index="08"
      kicker={t("alarmAudio.kicker")}
      title={t("alarmAudio.title")}
      lede={t("alarmAudio.lede")}
    >
      <div className="form-check mb-3">
        <input
          id="alarm-audio-muted"
          className="form-check-input"
          type="checkbox"
          checked={profile.muted}
          disabled={!canMutate}
          onChange={(event) => setProfile({ ...profile, muted: event.target.checked })}
        />
        <label className="form-check-label" htmlFor="alarm-audio-muted">
          {t("alarmAudio.muted")}
        </label>
      </div>
      <div className="table-responsive">
        <table className="table table-sm align-middle mb-2">
          <thead>
            <tr>
              <th>{t("alarmAudio.priority")}</th>
              <th>{t("alarmAudio.sound")}</th>
              <th>{t("alarmAudio.frequency")}</th>
              <th>{t("alarmAudio.repeat")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {PRIORITIES.map((priority) => {
              const row = profile.profiles.find((item) => item.priority === priority);
              const sound = soundById(row?.soundId ?? 2);
              return (
                <tr key={priority}>
                  <td>{t("alarmAudio.priorityLevel", { priority })}</td>
                  <td>
                    <select
                      className="form-select form-select-sm"
                      value={row?.soundId ?? 2}
                      disabled={!canMutate}
                      aria-label={t("alarmAudio.sound")}
                      onChange={(event) => updateRow(priority, { soundId: Number(event.target.value) })}
                    >
                      {SOUND_CATALOG.map((item) => (
                        <option key={item.id} value={item.id}>
                          {t(item.nameKey)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>{sound.frequencyHz} Hz</td>
                  <td>
                    <input
                      className="form-control form-control-sm"
                      type="number"
                      min={2}
                      value={row?.repeatSeconds ?? 10}
                      disabled={!canMutate}
                      aria-label={t("alarmAudio.repeat")}
                      onChange={(event) => updateRow(priority, { repeatSeconds: Number(event.target.value) })}
                    />
                  </td>
                  <td>
                    <Button variant="secondary" className="btn-sm" onClick={() => preview(sound.id)}>
                      {t("alarmAudio.preview")}
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {violation && <p className="text-danger small mb-2">{t(`alarmAudio.violation.${violation}`)}</p>}
      <Button
        onClick={() => void save()}
        disabled={!canMutate || saving || Boolean(violation) || !dirty}
        loading={saving}
      >
        {t("alarmAudio.save")}
      </Button>
    </SettingsChapter>
  );
}
