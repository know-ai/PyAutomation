import { useEffect, useState, useRef } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { getSettings, updateSettings, exportConfig, importConfig, type AppConfig } from "../services/settings";
import { useTranslation } from "../hooks/useTranslation";
import { showToast } from "../utils/toast";

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
      await updateSettings(config);
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
      // Reset file input
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

  const logLevelOptions = [
    { value: 0, label: t("settings.logLevels.0") },
    { value: 10, label: t("settings.logLevels.10") },
    { value: 20, label: t("settings.logLevels.20") },
    { value: 30, label: t("settings.logLevels.30") },
    { value: 40, label: t("settings.logLevels.40") },
    { value: 50, label: t("settings.logLevels.50") },
  ];

  const cardTitle = (
    <div className="d-flex justify-content-between align-items-center w-100">
      <h3 className="card-title m-0">{t("settings.title")}</h3>
      <div className="d-flex gap-2 ms-auto">
        <Button
          variant="primary"
          onClick={handleImportClick}
          loading={importing}
        >
          {t("settings.importConfig")}
        </Button>
        <Button
          variant="success"
          onClick={handleExport}
          loading={exporting}
        >
          {t("settings.exportConfig")}
        </Button>
      </div>
    </div>
  );

  return (
    <div className="row">
      <div className="col-12">
        <Card title={cardTitle}>
          {loading ? (
            <div className="text-center py-4">
              <div className="spinner-border text-primary" role="status">
                <span className="visually-hidden">{t("settings.loading")}</span>
              </div>
            </div>
          ) : (
            <>
              <div className="mb-4">
                <h5 className="mb-3">{t("settings.applicationSettings")}</h5>
                
                <div className="row mb-3">
                  <div className="col-md-6">
                    <label htmlFor="logger_period" className="form-label">
                      {t("settings.loggerPeriod")}
                    </label>
                    <input
                      type="number"
                      className="form-control"
                      id="logger_period"
                      min="1.0"
                      step="0.1"
                      value={config.logger_period || ""}
                      onChange={(e) =>
                        handleInputChange(
                          "logger_period",
                          parseFloat(e.target.value) || 0
                        )
                      }
                    />
                    <small className="form-text text-muted">
                      Mínimo: 1.0 segundos
                    </small>
                  </div>

                  <div className="col-md-6">
                    <label htmlFor="log_level" className="form-label">
                      {t("settings.logLevel")}
                    </label>
                    <select
                      className="form-select"
                      id="log_level"
                      value={config.log_level ?? 20}
                      onChange={(e) =>
                        handleInputChange(
                          "log_level",
                          parseInt(e.target.value, 10)
                        )
                      }
                    >
                      {logLevelOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.value} - {option.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="row mb-3">
                  <div className="col-md-6">
                    <label htmlFor="log_max_bytes" className="form-label">
                      {t("settings.logMaxBytes")}
                    </label>
                    <input
                      type="number"
                      className="form-control"
                      id="log_max_bytes"
                      min="1024"
                      step="1024"
                      value={config.log_max_bytes || ""}
                      onChange={(e) =>
                        handleInputChange(
                          "log_max_bytes",
                          parseInt(e.target.value, 10) || 0
                        )
                      }
                    />
                    <small className="form-text text-muted">
                      Mínimo: 1024 bytes
                    </small>
                  </div>

                  <div className="col-md-6">
                    <label htmlFor="log_backup_count" className="form-label">
                      {t("settings.logBackupCount")}
                    </label>
                    <input
                      type="number"
                      className="form-control"
                      id="log_backup_count"
                      min="1"
                      value={config.log_backup_count || ""}
                      onChange={(e) =>
                        handleInputChange(
                          "log_backup_count",
                          parseInt(e.target.value, 10) || 0
                        )
                      }
                    />
                    <small className="form-text text-muted">
                      Mínimo: 1 backup
                    </small>
                  </div>
                </div>

                <div className="d-flex gap-2 mt-4">
                  <Button
                    variant="primary"
                    onClick={handleSave}
                    loading={saving}
                  >
                    {t("settings.saveSettings")}
                  </Button>
                </div>
              </div>
            </>
          )}
          <input
            ref={fileInputRef}
            type="file"
            className="d-none"
            accept=".json"
            onChange={handleFileChange}
          />
        </Card>
      </div>
    </div>
  );
}
