import { useEffect, useState, useRef } from "react";
import { Button } from "../components/Button";
import { StationAppearance } from "../components/StationAppearance";
import { DatabaseConnectivityPanel } from "../components/DatabaseConnectivityPanel";
import { ServiceRuntimePanel } from "../components/ServiceRuntimePanel";
import { SettingsChapter } from "../components/SettingsChapter";
import { getSettings, updateSettings, exportConfig, importConfig, type AppConfig } from "../services/settings";
import { useTranslation } from "../hooks/useTranslation";
import { showToast } from "../utils/toast";

const TOC = [
  { href: "#settings-station", labelKey: "settings.navStation" },
  { href: "#settings-historian", labelKey: "settings.navHistorian" },
  { href: "#settings-service", labelKey: "settings.navService" },
  { href: "#settings-backup", labelKey: "settings.navBackup" },
] as const;

export function Settings() {
  const { t } = useTranslation();
  const [config, setConfig] = useState<AppConfig>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const settings = await getSettings();
      setConfig(settings);
    } catch (error: any) {
      showToast(
        error.response?.data?.message || t("settings.settingsError"),
        "error"
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const handleInputChange = (field: keyof AppConfig, value: number) => {
    setConfig((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateSettings({
        logger_period: Math.max(1, Number(config.logger_period) || 10),
        log_level: config.log_level ?? 20,
      });
      showToast(t("settings.settingsSaved"), "success");
      await loadSettings();
    } catch (error: any) {
      showToast(
        error.response?.data?.message || t("settings.settingsError"),
        "error"
      );
    } finally {
      setSaving(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const blob = await exportConfig();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `configuration_export_${new Date().toISOString().split("T")[0]}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      showToast(t("settings.configExported"), "success");
    } catch (error: any) {
      showToast(
        error.response?.data?.message || t("settings.configExportedError"),
        "error"
      );
    } finally {
      setExporting(false);
    }
  };

  const handleImportClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const fileInput = event.target;
    if (!fileInput.files || fileInput.files.length === 0) {
      return;
    }

    const file = fileInput.files[0];
    if (!file.name.endsWith(".json")) {
      showToast(t("settings.invalidFile"), "error");
      fileInput.value = "";
      return;
    }

    setImporting(true);
    try {
      const result = await importConfig(file);
      if (result.error) {
        showToast(
          result.message || t("settings.configImportedError"),
          "error"
        );
      } else {
        showToast(t("settings.configImported"), "success");
        if (result.summary) {
          const summary = `${t("settings.importSummary")}: ${t("settings.imported")}: ${result.summary.imported}, ${t("settings.skipped")}: ${result.summary.skipped}, ${t("settings.errors")}: ${result.summary.errors}`;
          showToast(summary, "info", 8000);
        }
        await loadSettings();
      }
      fileInput.value = "";
    } catch (error: any) {
      showToast(
        error.response?.data?.message || t("settings.configImportedError"),
        "error"
      );
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="settings-page">
      <header className="settings-hero">
        <p className="settings-hero__eyebrow">{t("settings.heroEyebrow")}</p>
        <h2 className="settings-hero__title">{t("settings.title")}</h2>
        <p className="settings-hero__lede">{t("settings.pageLede")}</p>
      </header>

      <nav className="settings-toc" aria-label={t("settings.tocLabel")}>
        {TOC.map((item) => (
          <a key={item.href} className="settings-toc__link" href={item.href}>
            {t(item.labelKey)}
          </a>
        ))}
      </nav>

      <StationAppearance />

      <SettingsChapter
        id="settings-historian"
        index="02"
        kicker={t("settings.historianKicker")}
        title={t("settings.historianTitle")}
        lede={t("settings.historianLede")}
      >
        <DatabaseConnectivityPanel showHead={false} />
      </SettingsChapter>

      <SettingsChapter
        id="settings-service"
        index="03"
        kicker={t("settings.serviceKicker")}
        title={t("settings.applicationSettings")}
        lede={t("settings.runtimeLede")}
      >
        <ServiceRuntimePanel
          config={config}
          loading={loading}
          saving={saving}
          onPeriodChange={(value) => handleInputChange("logger_period", value)}
          onLevelChange={(value) => handleInputChange("log_level", value)}
          onSave={() => void handleSave()}
        />
      </SettingsChapter>

      <SettingsChapter
        id="settings-backup"
        index="04"
        kicker={t("settings.backupKicker")}
        title={t("settings.backupTitle")}
        lede={t("settings.backupLede")}
      >
        <article className="settings-tile settings-tile--backup">
          <div className="settings-backup__copy">
            <p className="settings-backup__title">{t("settings.backupCardTitle")}</p>
            <p className="settings-backup__hint">{t("settings.backupCardHint")}</p>
          </div>
          <div className="settings-backup__actions">
            <Button variant="secondary" onClick={handleImportClick} loading={importing}>
              {t("settings.importConfig")}
            </Button>
            <Button variant="secondary" onClick={handleExport} loading={exporting}>
              {t("settings.exportConfig")}
            </Button>
          </div>
        </article>
      </SettingsChapter>

      <input
        ref={fileInputRef}
        type="file"
        className="d-none"
        accept=".json"
        onChange={handleFileChange}
      />
    </div>
  );
}
