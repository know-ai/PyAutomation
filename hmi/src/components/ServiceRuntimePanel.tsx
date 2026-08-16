import clsx from "clsx";
import { Button } from "./Button";
import { useTranslation } from "../hooks/useTranslation";
import type { AppConfig } from "../services/settings";

const LOG_LEVELS: Array<{
  value: number;
  nameKey: string;
  hintKey: string;
  code: string;
  recommended?: boolean;
}> = [
  { value: 10, nameKey: "settings.logLevelDebug", hintKey: "settings.logLevelDebugHint", code: "DEBUG" },
  { value: 20, nameKey: "settings.logLevelInfo", hintKey: "settings.logLevelInfoHint", code: "INFO" },
  { value: 30, nameKey: "settings.logLevelWarning", hintKey: "settings.logLevelWarningHint", code: "WARNING", recommended: true },
  { value: 40, nameKey: "settings.logLevelError", hintKey: "settings.logLevelErrorHint", code: "ERROR" },
  { value: 50, nameKey: "settings.logLevelCritical", hintKey: "settings.logLevelCriticalHint", code: "CRITICAL" },
];

type ServiceRuntimePanelProps = {
  config: AppConfig;
  loading: boolean;
  saving: boolean;
  onPeriodChange: (value: number) => void;
  onLevelChange: (value: number) => void;
  onSave: () => void;
};

export function ServiceRuntimePanel({
  config,
  loading,
  saving,
  onPeriodChange,
  onLevelChange,
  onSave,
}: ServiceRuntimePanelProps) {
  const { t } = useTranslation();
  const period = Number(config.logger_period) > 0 ? Number(config.logger_period) : 10;
  const level = config.log_level ?? 20;

  const nudgePeriod = (delta: number) => {
    const next = Math.max(1, Math.round((period + delta) * 10) / 10);
    onPeriodChange(next);
  };

  return (
    <div className="settings-split">
      <article className="settings-tile settings-tile--service">
        <div className="settings-tile__label">{t("settings.loggerPeriod")}</div>
        <p className="settings-tile__hint">{t("settings.loggerPeriodLede")}</p>

        {loading ? (
          <div className="settings-tile__loading">
            <div className="spinner-border spinner-border-sm text-primary" role="status">
              <span className="visually-hidden">{t("settings.loading")}</span>
            </div>
          </div>
        ) : (
          <>
            <div className="settings-metric">
              <button
                type="button"
                className="settings-metric__step"
                onClick={() => nudgePeriod(-1)}
                aria-label={t("settings.loggerPeriodDecrease")}
              >
                −
              </button>
              <input
                id="logger_period"
                className="settings-metric__input"
                type="number"
                min={1}
                step={1}
                value={period}
                onChange={(e) => onPeriodChange(Math.max(1, parseFloat(e.target.value) || 1))}
              />
              <span className="settings-metric__unit">{t("settings.secondsUnit")}</span>
              <button
                type="button"
                className="settings-metric__step"
                onClick={() => nudgePeriod(1)}
                aria-label={t("settings.loggerPeriodIncrease")}
              >
                +
              </button>
            </div>
            <div className="settings-callout">
              <i className="bi bi-info-circle" aria-hidden="true" />
              <p>{t("settings.loggerPeriodExplain", { seconds: period })}</p>
            </div>
          </>
        )}
      </article>

      <article className="settings-tile settings-tile--service">
        <div className="settings-tile__label">{t("settings.logLevel")}</div>
        <p className="settings-tile__hint">{t("settings.logLevelLede")}</p>

        {loading ? (
          <div className="settings-tile__loading">
            <div className="spinner-border spinner-border-sm text-primary" role="status">
              <span className="visually-hidden">{t("settings.loading")}</span>
            </div>
          </div>
        ) : (
          <div className="settings-level-list" role="radiogroup" aria-label={t("settings.logLevel")}>
            {LOG_LEVELS.map((item) => {
              const selected = level === item.value;
              return (
                <button
                  key={item.value}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  className={clsx("settings-level", selected && "is-selected")}
                  onClick={() => onLevelChange(item.value)}
                >
                  <span className="settings-level__code">{item.code}</span>
                  <span className="settings-level__copy">
                    <span className="settings-level__name">
                      {t(item.nameKey)}
                      {item.recommended ? (
                        <span className="settings-pill">{t("settings.recommendedPlant")}</span>
                      ) : null}
                    </span>
                    <span className="settings-level__hint">{t(item.hintKey)}</span>
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </article>

      <div className="settings-split__footer">
        <p className="settings-split__note">{t("settings.runtimeSaveNote")}</p>
        <Button variant="primary" onClick={onSave} loading={saving} disabled={loading}>
          {t("settings.saveSettings")}
        </Button>
      </div>
    </div>
  );
}
