import { useEffect, useState } from "react";
import { useTranslation } from "../hooks/useTranslation";
import { getTagFilterStatus, type TagFilterStatus } from "../services/tags";

const WAVELET_FAMILIES = ["db4", "db6", "sym4", "coif2", "bior2.2"];
/** Operator-facing slider range (must match backend WaveletBlockFilter clamps). */
const WAVELET_LEVEL_MIN = 1;
const WAVELET_LEVEL_MAX = 10;
const WAVELET_THRESHOLD_MIN = 1;
const WAVELET_THRESHOLD_MAX = 10;

export type WaveletFormFields = {
  filter_enabled: boolean;
  filter_wavelet: string;
  filter_level: number;
  filter_threshold_factor: number;
  filter_persist: boolean;
};

type Props = {
  formData: WaveletFormFields;
  sourceName?: string;
  dataType?: string;
  onChange: (patch: Partial<WaveletFormFields>) => void;
};

function statusTone(status?: string): string {
  if (status === "ok") return "success";
  if (status === "warmup" || status === "hold") return "warning";
  if (status === "failed") return "danger";
  return "secondary";
}

function qualityTone(quality?: string): string {
  if (quality === "GOOD") return "success";
  if (quality === "UNCERTAIN") return "warning";
  if (quality === "BAD") return "danger";
  return "secondary";
}

export function WaveletFilterPanel({ formData, sourceName, dataType, onChange }: Props) {
  const { t } = useTranslation();
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [live, setLive] = useState<TagFilterStatus | null>(null);
  const numeric = (dataType || "float").toLowerCase() === "float";
  const derivedName = sourceName ? `${sourceName.replace(/\.f$/, "")}.f` : "";

  useEffect(() => {
    if (!formData.filter_enabled || !sourceName) {
      setLive(null);
      return;
    }
    let cancelled = false;
    const load = async () => {
      const status = await getTagFilterStatus(sourceName);
      if (!cancelled) setLive(status);
    };
    load();
    const timer = window.setInterval(load, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [formData.filter_enabled, sourceName]);

  return (
    <div className="col-12">
      <div className="border rounded p-3 bg-light-subtle">
        <div className="d-flex justify-content-between align-items-center gap-3">
          <div>
            <h6 className="mb-1">{t("tags.waveletFilter")}</h6>
            <small className="text-muted">{t("tags.waveletCadenceHint")}</small>
          </div>
          <div className="form-check form-switch m-0">
            <input
              className="form-check-input"
              type="checkbox"
              role="switch"
              disabled={!numeric}
              checked={formData.filter_enabled}
              onChange={(e) => onChange({ filter_enabled: e.target.checked })}
              title={!numeric ? t("tags.waveletNumericOnly") : undefined}
            />
          </div>
        </div>

        {formData.filter_enabled && (
          <>
            <div className="d-flex flex-wrap align-items-center gap-2 mt-3">
              <span className={`badge text-bg-${statusTone(live?.status)}`}>
                {t(`tags.waveletStatus.${live?.status || "idle"}`)}
              </span>
              {live?.age_ms != null && (
                <small className="text-muted">
                  {t("tags.waveletLatency")}: {(live.age_ms / 1000).toFixed(2)}s
                </small>
              )}
              {live?.last_publication_quality && (
                <span className={`badge text-bg-${qualityTone(live.last_publication_quality)}`}>
                  {t("tags.waveletPublicationQuality")}: {live.last_publication_quality}
                </span>
              )}
              {(live?.bad_samples_dropped ?? live?.drop_count ?? 0) > 0 && (
                <small className="text-muted">
                  {t("tags.waveletDropped")}: {live?.bad_samples_dropped ?? live?.drop_count}
                </small>
              )}
              {derivedName && (
                <small className="text-muted">
                  {t("tags.waveletDerivedTag")}: <code>{derivedName}</code>
                </small>
              )}
            </div>
            <p className="small text-muted mt-2 mb-0">{t("tags.waveletLatencyHint")}</p>
            <button
              type="button"
              className="btn btn-link btn-sm px-0 mt-2"
              onClick={() => setAdvancedOpen((open) => !open)}
            >
              {t("tags.waveletAdvanced")} {advancedOpen ? "▲" : "▼"}
            </button>
            {advancedOpen && (
              <div className="row g-3 mt-1">
                <div className="col-md-4">
                  <label className="form-label">{t("tags.waveletFamily")}</label>
                  <select
                    className="form-select"
                    value={formData.filter_wavelet}
                    onChange={(e) => onChange({ filter_wavelet: e.target.value })}
                    title={t("tags.waveletFamilyHint")}
                  >
                    {WAVELET_FAMILIES.map((name) => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="col-md-4">
                  <label className="form-label">
                    {t("tags.waveletLevel")}: {formData.filter_level}
                    <span className="text-muted fw-normal"> ({WAVELET_LEVEL_MIN}–{WAVELET_LEVEL_MAX})</span>
                  </label>
                  <input
                    type="range"
                    className="form-range"
                    min={WAVELET_LEVEL_MIN}
                    max={WAVELET_LEVEL_MAX}
                    step={1}
                    value={formData.filter_level}
                    onChange={(e) => onChange({ filter_level: Number(e.target.value) })}
                    title={t("tags.waveletLevelHint")}
                  />
                </div>
                <div className="col-md-4">
                  <label className="form-label">
                    {t("tags.waveletThreshold")}: {Number(formData.filter_threshold_factor).toFixed(1)}
                    <span className="text-muted fw-normal"> ({WAVELET_THRESHOLD_MIN}–{WAVELET_THRESHOLD_MAX})</span>
                  </label>
                  <input
                    type="range"
                    className="form-range"
                    min={WAVELET_THRESHOLD_MIN}
                    max={WAVELET_THRESHOLD_MAX}
                    step={0.1}
                    value={formData.filter_threshold_factor}
                    onChange={(e) => onChange({ filter_threshold_factor: Number(e.target.value) })}
                    title={t("tags.waveletThresholdHint")}
                  />
                </div>
                <div className="col-12">
                  <div className="form-check">
                    <input
                      className="form-check-input"
                      type="checkbox"
                      checked={formData.filter_persist}
                      onChange={(e) => onChange({ filter_persist: e.target.checked })}
                    />
                    <label className="form-check-label">{t("tags.waveletPersist")}</label>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
