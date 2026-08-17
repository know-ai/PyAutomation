import clsx from "clsx";
import { useTheme } from "../hooks/useTheme";
import { useTranslation } from "../hooks/useTranslation";
import { useAppDispatch } from "../hooks/useAppDispatch";
import { setLocale } from "../store/slices/localeSlice";
import { useDisplayTimezone } from "../hooks/useDisplayTimezone";
import { useDisplayDensity } from "../hooks/useDisplayDensity";
import { SettingsChapter } from "./SettingsChapter";
import type { DisplayDensity } from "../utils/displayDensity";

const DENSITY_OPTIONS: Array<{
  id: DisplayDensity;
  nameKey: string;
  hintKey: string;
  icon: string;
}> = [
  { id: "auto", nameKey: "settings.displayDensityAuto", hintKey: "settings.displayDensityAutoHint", icon: "bi-aspect-ratio" },
  { id: "workstation", nameKey: "settings.displayDensityWorkstation", hintKey: "settings.displayDensityWorkstationHint", icon: "bi-laptop" },
  { id: "control", nameKey: "settings.displayDensityControl", hintKey: "settings.displayDensityControlHint", icon: "bi-tv" },
  { id: "wall", nameKey: "settings.displayDensityWall", hintKey: "settings.displayDensityWallHint", icon: "bi-display" },
];

const LANGUAGES = [
  { id: "es" as const, nameKey: "settings.languageSpanish", native: "Español", code: "ES" },
  { id: "en" as const, nameKey: "settings.languageEnglish", native: "English", code: "EN" },
];

export function StationAppearance() {
  const { t, locale } = useTranslation();
  const { mode, set } = useTheme();
  const { mode: tzMode, setMode: setTzMode, plantTimezone, browserTimezone } = useDisplayTimezone();
  const { mode: densityMode, setMode: setDensityMode } = useDisplayDensity();
  const dispatch = useAppDispatch();

  return (
    <SettingsChapter
      id="settings-station"
      index="01"
      kicker={t("settings.stationKicker")}
      title={t("settings.appearanceTitle")}
      lede={t("settings.appearanceLede")}
    >
      <div className="settings-atelier">
        <article className="settings-tile">
          <div className="settings-tile__label">{t("settings.language")}</div>
          <p className="settings-tile__hint">{t("settings.languageLede")}</p>
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
        </article>

        <article className="settings-tile">
          <div className="settings-tile__label">{t("settings.theme")}</div>
          <p className="settings-tile__hint">{t("settings.themeLede")}</p>
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
        </article>

        <article className="settings-tile settings-tile--span">
          <div className="settings-tile__label">{t("settings.displayDensity")}</div>
          <p className="settings-tile__hint">{t("settings.displayDensityLede")}</p>
          <div className="settings-choice" role="radiogroup" aria-label={t("settings.displayDensity")}>
            {DENSITY_OPTIONS.map((option) => {
              const selected = densityMode === option.id;
              return (
                <button
                  key={option.id}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  className={clsx("settings-choice__card", selected && "is-selected")}
                  onClick={() => setDensityMode(option.id)}
                >
                  <i className={`bi ${option.icon} settings-choice__icon`} aria-hidden="true" />
                  <span className="settings-choice__copy">
                    <span className="settings-choice__name">{t(option.nameKey)}</span>
                    <span className="settings-choice__hint">{t(option.hintKey)}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </article>

        <article className="settings-tile settings-tile--span">
          <div className="settings-tile__label">{t("timezone.title")}</div>
          <p className="settings-tile__hint">{t("timezone.lede")}</p>
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
        </article>
      </div>
    </SettingsChapter>
  );
}
