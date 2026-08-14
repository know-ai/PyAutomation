import clsx from "clsx";
import { useTheme } from "../hooks/useTheme";
import { useTranslation } from "../hooks/useTranslation";
import { useAppDispatch } from "../hooks/useAppDispatch";
import { setLocale } from "../store/slices/localeSlice";
import { useDisplayTimezone } from "../hooks/useDisplayTimezone";

const LANGUAGES = [
  { id: "es" as const, nameKey: "settings.languageSpanish", native: "Español", code: "ES" },
  { id: "en" as const, nameKey: "settings.languageEnglish", native: "English", code: "EN" },
];

export function StationAppearance() {
  const { t, locale } = useTranslation();
  const { mode, set } = useTheme();
  const { mode: tzMode, setMode: setTzMode, plantTimezone, browserTimezone } = useDisplayTimezone();
  const dispatch = useAppDispatch();

  return (
    <section className="settings-panel" aria-labelledby="settings-appearance-title">
      <div className="settings-panel__head">
        <p className="settings-kicker">{t("settings.stationKicker")}</p>
        <h3 id="settings-appearance-title" className="settings-panel__title">
          {t("settings.appearanceTitle")}
        </h3>
        <p className="settings-panel__lede">{t("settings.appearanceLede")}</p>
      </div>

      <div className="settings-field">
        <div className="settings-field__label">{t("settings.language")}</div>
        <div className="settings-choice" role="radiogroup" aria-label={t("settings.language")}>
          {LANGUAGES.map((lang) => {
            const selected = locale === lang.id;
            return (
              <button
                key={lang.id}
                type="button"
                role="radio"
                aria-checked={selected}
                className={clsx("settings-choice__card", selected && "is-selected")}
                onClick={() => dispatch(setLocale(lang.id))}
              >
                <span className="settings-choice__code">{lang.code}</span>
                <span className="settings-choice__copy">
                  <span className="settings-choice__name">{lang.native}</span>
                  <span className="settings-choice__hint">{t(lang.nameKey)}</span>
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="settings-field">
        <div className="settings-field__label">{t("settings.theme")}</div>
        <div className="settings-choice" role="radiogroup" aria-label={t("settings.theme")}>
          <button
            type="button"
            role="radio"
            aria-checked={mode === "light"}
            className={clsx("settings-choice__card", mode === "light" && "is-selected")}
            onClick={() => set("light")}
          >
            <i className="bi bi-sun settings-choice__icon" aria-hidden="true" />
            <span className="settings-choice__copy">
              <span className="settings-choice__name">{t("settings.themeLight")}</span>
              <span className="settings-choice__hint">{t("settings.themeLightHint")}</span>
            </span>
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={mode === "dark"}
            className={clsx("settings-choice__card", mode === "dark" && "is-selected")}
            onClick={() => set("dark")}
          >
            <i className="bi bi-moon settings-choice__icon" aria-hidden="true" />
            <span className="settings-choice__copy">
              <span className="settings-choice__name">{t("settings.themeDark")}</span>
              <span className="settings-choice__hint">{t("settings.themeDarkHint")}</span>
            </span>
          </button>
        </div>
      </div>

      <div className="settings-field">
        <div className="settings-field__label">{t("timezone.title")}</div>
        <p className="settings-panel__lede mb-2">{t("timezone.lede")}</p>
        <div className="settings-choice" role="radiogroup" aria-label={t("timezone.title")}>
          <button
            type="button"
            role="radio"
            aria-checked={tzMode === "plant"}
            className={clsx("settings-choice__card", tzMode === "plant" && "is-selected")}
            onClick={() => setTzMode("plant")}
          >
            <i className="bi bi-building settings-choice__icon" aria-hidden="true" />
            <span className="settings-choice__copy">
              <span className="settings-choice__name">{t("timezone.plant")}</span>
              <span className="settings-choice__hint">
                {t("timezone.plantHint", { zone: plantTimezone || "—" })}
              </span>
            </span>
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={tzMode === "local"}
            className={clsx("settings-choice__card", tzMode === "local" && "is-selected")}
            onClick={() => setTzMode("local")}
          >
            <i className="bi bi-laptop settings-choice__icon" aria-hidden="true" />
            <span className="settings-choice__copy">
              <span className="settings-choice__name">{t("timezone.local")}</span>
              <span className="settings-choice__hint">
                {t("timezone.localHint", { zone: browserTimezone || "—" })}
              </span>
            </span>
          </button>
        </div>
      </div>
    </section>
  );
}
