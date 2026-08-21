import { useCallback, useEffect, useState } from "react";
import { SettingsChapter } from "./SettingsChapter";
import { useTranslation } from "../hooks/useTranslation";
import { getSettings, updateSettings } from "../services/settings";
import { showToast } from "../utils/toast";

/** ISA-18.2 process-alarm quality policy (CA-OQ-11). */
export function QualityPolicyPanel() {
  const { t } = useTranslation();
  const [inhibitUncertain, setInhibitUncertain] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const settings = await getSettings();
      setInhibitUncertain(Boolean(settings.alarm_inhibit_uncertain_quality));
    } catch (error: any) {
      showToast(error?.response?.data?.message || t("settings.settingsError"), "error");
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const persist = async (next: boolean) => {
    setSaving(true);
    try {
      await updateSettings({ alarm_inhibit_uncertain_quality: next });
      setInhibitUncertain(next);
      showToast(t("settings.qualityPolicySaved"), "success");
    } catch (error: any) {
      showToast(error?.response?.data?.message || t("settings.settingsError"), "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SettingsChapter
      id="settings-quality"
      index="03b"
      kicker={t("settings.qualityPolicyKicker")}
      title={t("settings.qualityPolicyTitle")}
      lede={t("settings.qualityPolicyLede")}
    >
      <article className="settings-tile">
        <label className="form-check mb-0">
          <input
            className="form-check-input"
            type="checkbox"
            checked={inhibitUncertain}
            disabled={loading || saving}
            onChange={(event) => {
              void persist(event.target.checked);
            }}
          />
          <span className="form-check-label" title={t("settings.qualityPolicyHint")}>
            {t("settings.qualityPolicyInhibitUncertain")}
          </span>
        </label>
        <p className="form-text mb-0 mt-2">{t("settings.qualityPolicyHint")}</p>
      </article>
    </SettingsChapter>
  );
}
