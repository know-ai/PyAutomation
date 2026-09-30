import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "../Button";
import { useTranslation } from "../../hooks/useTranslation";
import { showToast } from "../../utils/toast";
import { inspectGeospatialCsv } from "../../utils/geospatialCsv";
import {
  createGeospatialPoint,
  deleteGeospatialPoint,
  importGeospatialCsv,
  listGeospatialPoints,
  updateGeospatialPoint,
  type GeospatialPoint,
} from "../../services/linearReferencing";

type GeospatialProfilePanelProps = {
  canMutate: boolean;
};

type PointForm = {
  segment_name: string;
  kp: string;
  latitude: string;
  longitude: string;
};

const EMPTY_FORM: PointForm = {
  segment_name: "",
  kp: "",
  latitude: "",
  longitude: "",
};

function apiMessage(error: unknown, fallback: string): string {
  const data = (error as { response?: { data?: { message?: string; data?: { errors?: string[] } } } })
    ?.response?.data;
  const errors = data?.data?.errors;
  if (Array.isArray(errors) && errors.length > 0) {
    return errors.join(" ");
  }
  return data?.message || fallback;
}

function parsePoint(form: PointForm): {
  segment_name: string;
  kp: number;
  latitude: number;
  longitude: number;
} | null {
  const segment_name = form.segment_name.trim();
  const kp = Number(form.kp);
  const latitude = Number(form.latitude);
  const longitude = Number(form.longitude);
  if (!segment_name || form.kp.trim() === "" || form.latitude.trim() === "" || form.longitude.trim() === "") {
    return null;
  }
  if (![kp, latitude, longitude].every(Number.isFinite)) {
    return null;
  }
  if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
    return null;
  }
  return { segment_name, kp, latitude, longitude };
}

export function GeospatialProfilePanel({ canMutate }: GeospatialProfilePanelProps) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [points, setPoints] = useState<GeospatialPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [segmentFilter, setSegmentFilter] = useState("");
  const [form, setForm] = useState<PointForm>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);
  const [formError, setFormError] = useState("");
  const [importError, setImportError] = useState("");

  const loadPoints = async () => {
    setLoading(true);
    try {
      const rows = await listGeospatialPoints();
      setPoints(rows);
    } catch (error) {
      showToast(apiMessage(error, t("settings.georefLoadError")), "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadPoints();
  }, []);

  const segments = useMemo(() => {
    return Array.from(new Set(points.map((point) => point.segment_name).filter(Boolean))).sort((a, b) =>
      a.localeCompare(b),
    );
  }, [points]);

  const visiblePoints = useMemo(() => {
    const rows = segmentFilter
      ? points.filter((point) => point.segment_name === segmentFilter)
      : points;
    return [...rows].sort((a, b) => a.kp - b.kp || a.segment_name.localeCompare(b.segment_name));
  }, [points, segmentFilter]);

  const resetForm = () => {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setFormError("");
  };

  const onEdit = (point: GeospatialPoint) => {
    setEditingId(point.id);
    setPendingDeleteId(null);
    setFormError("");
    setForm({
      segment_name: point.segment_name,
      kp: String(point.kp),
      latitude: String(point.latitude),
      longitude: String(point.longitude),
    });
  };

  const onSubmit = async () => {
    const payload = parsePoint(form);
    if (!payload) {
      setFormError(t("settings.georefInvalidPoint"));
      return;
    }
    setSaving(true);
    setFormError("");
    try {
      if (editingId == null) {
        await createGeospatialPoint(payload);
        showToast(t("settings.georefSaved"), "success");
      } else {
        await updateGeospatialPoint(editingId, payload);
        showToast(t("settings.georefUpdated"), "success");
      }
      resetForm();
      await loadPoints();
    } catch (error) {
      setFormError(apiMessage(error, t("settings.georefLoadError")));
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async (id: number) => {
    setSaving(true);
    try {
      await deleteGeospatialPoint(id);
      if (editingId === id) {
        resetForm();
      }
      setPendingDeleteId(null);
      showToast(t("settings.georefDeleted"), "success");
      await loadPoints();
    } catch (error) {
      showToast(apiMessage(error, t("settings.georefLoadError")), "error");
    } finally {
      setSaving(false);
    }
  };

  const onImport = async (file: File) => {
    setImportError("");
    const text = await file.text();
    const issue = inspectGeospatialCsv(file.name, file.size, text);
    if (issue) {
      setImportError(t(`settings.georefError.${issue.code}`, { row: issue.row ?? "" }));
      return;
    }
    setImporting(true);
    try {
      const result = await importGeospatialCsv(file);
      showToast(
        `${t("settings.georefImported")}. ${t("settings.georefImportSummary", {
          created: result.created,
          updated: result.updated,
          skipped: result.skipped,
        })}`,
        "success",
      );
      await loadPoints();
    } catch (error) {
      setImportError(apiMessage(error, t("settings.georefLoadError")));
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="georef">
      <article className="settings-panel georef-format">
        <h4 className="settings-panel__title">{t("settings.georefFormatTitle")}</h4>
        <p className="settings-panel__lede">{t("settings.georefFormatLede")}</p>
        <pre className="georef-sample">
          <code>{t("settings.georefFormatSample")}</code>
        </pre>
        <div className="georef-import">
          <Button
            variant="secondary"
            disabled={!canMutate}
            loading={importing}
            onClick={() => fileInputRef.current?.click()}
          >
            {t("settings.georefChooseFile")}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            className="d-none"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) {
                void onImport(file);
              }
            }}
          />
        </div>
        {importError ? (
          <div className="alert alert-danger georef-alert" role="alert">
            {importError}
          </div>
        ) : null}
      </article>

      <article className="settings-panel">
        <h4 className="settings-panel__title">{t("settings.georefPointTitle")}</h4>
        <p className="settings-panel__lede">{t("settings.georefPointLede")}</p>
        <div className="georef-form">
          <label className="settings-field">
            <span className="settings-field__label">{t("settings.georefSegment")}</span>
            <input
              className="form-control"
              list="georef-segments"
              value={form.segment_name}
              disabled={!canMutate}
              onChange={(event) => setForm((current) => ({ ...current, segment_name: event.target.value }))}
            />
            <datalist id="georef-segments">
              {segments.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </label>
          <label className="settings-field">
            <span className="settings-field__label">{t("settings.georefKp")}</span>
            <input
              className="form-control"
              inputMode="decimal"
              value={form.kp}
              disabled={!canMutate}
              onChange={(event) => setForm((current) => ({ ...current, kp: event.target.value }))}
            />
          </label>
          <label className="settings-field">
            <span className="settings-field__label">{t("settings.georefLatitude")}</span>
            <input
              className="form-control"
              inputMode="decimal"
              value={form.latitude}
              disabled={!canMutate}
              onChange={(event) => setForm((current) => ({ ...current, latitude: event.target.value }))}
            />
          </label>
          <label className="settings-field">
            <span className="settings-field__label">{t("settings.georefLongitude")}</span>
            <input
              className="form-control"
              inputMode="decimal"
              value={form.longitude}
              disabled={!canMutate}
              onChange={(event) => setForm((current) => ({ ...current, longitude: event.target.value }))}
            />
          </label>
        </div>
        {formError ? (
          <div className="alert alert-danger georef-alert" role="alert">
            {formError}
          </div>
        ) : null}
        <div className="georef-form__actions">
          <Button disabled={!canMutate} loading={saving} onClick={() => void onSubmit()}>
            {editingId == null ? t("settings.georefAdd") : t("settings.georefSave")}
          </Button>
          {editingId != null ? (
            <Button variant="secondary" disabled={saving} onClick={resetForm}>
              {t("common.cancel")}
            </Button>
          ) : null}
        </div>
      </article>

      <article className="settings-panel">
        <div className="georef-table__toolbar">
          <label className="settings-field georef-filter">
            <span className="settings-field__label">{t("settings.georefSegment")}</span>
            <select
              className="form-select"
              value={segmentFilter}
              onChange={(event) => setSegmentFilter(event.target.value)}
            >
              <option value="">{t("settings.georefAllSegments")}</option>
              {segments.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {loading ? (
          <p className="settings-panel__lede">{t("common.loading")}</p>
        ) : visiblePoints.length === 0 ? (
          <p className="settings-panel__lede">{t("settings.georefEmpty")}</p>
        ) : (
          <div className="table-responsive">
            <table className="table table-sm georef-table">
              <thead>
                <tr>
                  <th>{t("settings.georefSegment")}</th>
                  <th>{t("settings.georefKp")}</th>
                  <th>{t("settings.georefLatitude")}</th>
                  <th>{t("settings.georefLongitude")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visiblePoints.map((point) => (
                  <tr key={point.id}>
                    <td>{point.segment_name}</td>
                    <td>{point.kp}</td>
                    <td>{point.latitude}</td>
                    <td>{point.longitude}</td>
                    <td className="georef-table__actions">
                      {pendingDeleteId === point.id ? (
                        <>
                          <span className="georef-delete-ask">{t("settings.georefDeleteAsk")}</span>
                          <Button
                            variant="danger"
                            disabled={!canMutate || saving}
                            onClick={() => void onDelete(point.id)}
                          >
                            {t("settings.georefConfirmDelete")}
                          </Button>
                          <Button variant="secondary" disabled={saving} onClick={() => setPendingDeleteId(null)}>
                            {t("common.cancel")}
                          </Button>
                        </>
                      ) : (
                        <>
                          <Button variant="secondary" disabled={!canMutate} onClick={() => onEdit(point)}>
                            {t("common.edit")}
                          </Button>
                          <Button
                            variant="danger"
                            disabled={!canMutate}
                            onClick={() => {
                              setPendingDeleteId(point.id);
                              setFormError("");
                            }}
                          >
                            {t("common.delete")}
                          </Button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </article>
    </div>
  );
}
