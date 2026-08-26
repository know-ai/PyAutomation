import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Card } from "./Card";
import { Button } from "./Button";
import { useTranslation } from "../hooks/useTranslation";
import { showToast } from "../utils/toast";
import {
  getMachineDomainConfig,
  putMachineDomainConfig,
  type DomainConfigField,
  type DomainConfigSection,
  type DomainHelpDisplay,
  type DomainLabelDisplay,
  type DomainUiSchema,
} from "../services/machines";

const SCHEMA_VERSION_SUPPORTED = 1;

type DomainConfigSlotProps = {
  machineName: string;
  schema: DomainUiSchema;
  config: Record<string, unknown>;
  machineState?: string;
  onConfigUpdated?: (config: Record<string, unknown>) => void;
  onSchemaUpdated?: (schema: DomainUiSchema) => void;
};

type Presentation = {
  labelDisplay: DomainLabelDisplay;
  helpDisplay: DomainHelpDisplay;
};

function parseLabelDisplay(raw: unknown): DomainLabelDisplay | undefined {
  if (raw === "visible" || raw === "hidden") return raw;
  if (raw === true) return "visible";
  if (raw === false) return "hidden";
  return undefined;
}

function parseHelpDisplay(raw: unknown): DomainHelpDisplay | undefined {
  if (raw === "tooltip" || raw === "text" || raw === "both" || raw === "none") return raw;
  return undefined;
}

function schemaPresentation(schema: DomainUiSchema): Presentation {
  const hints = schema.ui_hints || {};
  const fromShowLabels =
    typeof hints.show_labels === "boolean" ? (hints.show_labels ? "visible" : "hidden") : undefined;
  return {
    labelDisplay: parseLabelDisplay(hints.label_display) ?? fromShowLabels ?? "visible",
    helpDisplay: parseHelpDisplay(hints.help_display) ?? "text",
  };
}

function sectionPresentation(section: DomainConfigSection, fallback: Presentation): Presentation {
  return {
    labelDisplay: parseLabelDisplay(section.label_display) ?? fallback.labelDisplay,
    helpDisplay: parseHelpDisplay(section.help_display) ?? fallback.helpDisplay,
  };
}

function fieldPresentation(field: DomainConfigField, fallback: Presentation): Presentation {
  const fromShowLabel =
    typeof field.show_label === "boolean" ? (field.show_label ? "visible" : "hidden") : undefined;
  return {
    labelDisplay: parseLabelDisplay(field.label_display) ?? fromShowLabel ?? fallback.labelDisplay,
    helpDisplay: parseHelpDisplay(field.help_display) ?? fallback.helpDisplay,
  };
}

function fieldTooltip(field: DomainConfigField, presentation: Presentation): string | undefined {
  const help = field.help?.trim();
  const label = field.label?.trim();
  const useHelp = presentation.helpDisplay === "tooltip" || presentation.helpDisplay === "both";
  if (useHelp && help) return help;
  if (presentation.labelDisplay === "hidden" && label && !help) return label;
  return undefined;
}

function getByPath(obj: Record<string, unknown>, path: string): unknown {
  if (!path) return undefined;
  if (Object.prototype.hasOwnProperty.call(obj, path)) return obj[path];
  return path.split(".").reduce<unknown>((acc, key) => {
    if (acc && typeof acc === "object") return (acc as Record<string, unknown>)[key];
    return undefined;
  }, obj);
}

function setByPath(obj: Record<string, unknown>, path: string, value: unknown): Record<string, unknown> {
  if (!path.includes(".")) {
    return { ...obj, [path]: value };
  }
  const next = structuredClone(obj);
  const parts = path.split(".");
  let cursor: Record<string, unknown> = next;
  for (let i = 0; i < parts.length - 1; i += 1) {
    const key = parts[i];
    const child = cursor[key];
    if (!child || typeof child !== "object" || Array.isArray(child)) {
      cursor[key] = {};
    }
    cursor = cursor[key] as Record<string, unknown>;
  }
  cursor[parts[parts.length - 1]] = value;
  return next;
}

function conditionMatches(
  cond: { field: string; equals?: unknown } | undefined,
  values: Record<string, unknown>
): boolean {
  if (!cond?.field) return false;
  const current = getByPath(values, cond.field);
  if ("equals" in cond) return current === cond.equals;
  return Boolean(current);
}

function isFieldVisible(field: DomainConfigField, values: Record<string, unknown>): boolean {
  if (!field.depends_on?.field) return true;
  return conditionMatches(field.depends_on, values);
}

function isFieldReadOnly(field: DomainConfigField, values: Record<string, unknown>): boolean {
  if (field.read_only) return true;
  if (!field.read_only_when?.field) return false;
  return conditionMatches(field.read_only_when, values);
}

function dwtMaxLevel(length: number, filterLen: number): number {
  const denom = Math.max(1, filterLen - 1);
  if (!Number.isFinite(length) || length < denom) return 1;
  return Math.max(1, Math.floor(Math.log2(length / denom)));
}

function minLengthForLevel(level: number, filterLen: number, minLength: number, cap: number): number {
  const want = Math.max(1, Math.floor(level));
  for (let n = minLength; n <= cap; n += 1) {
    if (dwtMaxLevel(n, filterLen) >= want) return n;
  }
  return cap;
}

function resolveNumericBounds(
  field: DomainConfigField,
  values: Record<string, unknown>
): { min?: number; max?: number } {
  let min = field.min;
  let max = field.max;
  const bounds = field.dwt_bounds;
  const filterMap = bounds?.filter_len;
  if (!bounds || !filterMap) return { min, max };
  const family = String(getByPath(values, bounds.family_key || "wavelet_family") || "");
  const filterLen = Number(filterMap[family]);
  if (!Number.isFinite(filterLen) || filterLen <= 0) return { min, max };
  const cap = Number(bounds.cap) > 0 ? Number(bounds.cap) : 512;
  const minLength = Number(bounds.min_length) > 0 ? Number(bounds.min_length) : 8;
  if (bounds.role === "level") {
    const applyMax = !bounds.apply_max_when || conditionMatches(bounds.apply_max_when, values);
    const length = Number(getByPath(values, bounds.length_key || "window_size"));
    const n = applyMax && Number.isFinite(length) ? length : cap;
    max = dwtMaxLevel(n, filterLen);
  }
  if (bounds.role === "length") {
    const applyMin = !bounds.apply_min_when || conditionMatches(bounds.apply_min_when, values);
    if (applyMin) {
      const level = Number(getByPath(values, bounds.level_key || "wavelet_level"));
      if (Number.isFinite(level)) {
        const derived = minLengthForLevel(level, filterLen, minLength, cap);
        min = min == null ? derived : Math.max(min, derived);
      }
    }
  }
  return { min, max };
}

function applyDwtConstraints(fields: DomainConfigField[], values: Record<string, unknown>): Record<string, unknown> {
  let next = values;
  for (let pass = 0; pass < 2; pass += 1) {
    for (const field of fields) {
      if (!field.dwt_bounds || field.type !== "number") continue;
      const bounds = resolveNumericBounds(field, next);
      const raw = getByPath(next, field.key);
      const current = Number(raw);
      if (!Number.isFinite(current)) continue;
      let clamped = current;
      if (bounds.min != null && clamped < bounds.min) clamped = bounds.min;
      if (bounds.max != null && clamped > bounds.max) clamped = bounds.max;
      if (clamped !== current) next = setByPath(next, field.key, clamped);
    }
  }
  return next;
}

function warningList(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map((item) => String(item)).filter(Boolean);
  if (typeof raw === "string" && raw.trim()) return [raw];
  return [];
}

function applyBannerClass(status: unknown): string {
  if (status === "pending") return "alert alert-warning py-2 small mb-3";
  return "alert alert-info py-2 small mb-3";
}

const INTERNAL_COMPARE_KEYS = new Set([
  "_reset",
  "_set_factory",
  "_warnings",
  "_apply_status",
  "_apply_message",
  "_buffer_filled",
  "_buffer_need",
  "_sm_state",
  "_effective_pressure_mode",
  "_pressure_tags_status",
  "_missing_tags_message",
]);

function normalizeCompareValue(value: unknown): string {
  if (typeof value === "boolean") return value ? "1" : "0";
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (value == null || value === "") return "";
  const asNumber = Number(value);
  if (value !== "" && Number.isFinite(asNumber) && String(value).trim() !== "") {
    return String(asNumber);
  }
  return String(value);
}

function visibleEditableKeys(fields: DomainConfigField[], values: Record<string, unknown>): string[] {
  const keys: string[] = [];
  for (const field of fields) {
    if (!isFieldVisible(field, values)) continue;
    if (field.read_only || isFieldReadOnly(field, values)) continue;
    if (field.type === "object" && field.fields) {
      keys.push(...visibleEditableKeys(field.fields, values));
      continue;
    }
    if (field.type === "array") continue;
    keys.push(field.key);
  }
  return keys;
}

function valuesDiffer(
  left: Record<string, unknown>,
  right: Record<string, unknown>,
  keys: string[]
): boolean {
  for (const key of keys) {
    if (INTERNAL_COMPARE_KEYS.has(key) || key.startsWith("_")) continue;
    if (normalizeCompareValue(left[key]) !== normalizeCompareValue(right[key])) return true;
  }
  return false;
}

function parseNumberInput(raw: string, fallback: unknown): unknown {
  if (raw === "" || raw === "-") return raw;
  const n = Number(raw);
  return Number.isFinite(n) ? n : fallback;
}

function formatDisplayValue(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "number" && Number.isFinite(value)) {
    return Number.isInteger(value) ? String(value) : String(Number(value.toPrecision(6)));
  }
  return String(value);
}

function ControlShell({
  field,
  htmlFor,
  presentation,
  children,
  grow,
}: {
  field: DomainConfigField;
  htmlFor?: string;
  presentation: Presentation;
  children: ReactNode;
  grow?: boolean;
}) {
  const tooltip = fieldTooltip(field, presentation);
  const showLabel = Boolean(field.label) && presentation.labelDisplay === "visible" && field.type !== "boolean";
  const width = grow ? "100%" : field.type === "select" ? "280px" : "220px";
  return (
    <div title={tooltip} style={{ cursor: tooltip ? "help" : undefined }}>
      {field.label ? (
        <label className={showLabel ? "form-label d-block" : "visually-hidden"} htmlFor={htmlFor}>
          {field.label}
        </label>
      ) : null}
      {field.short_label || field.unit ? (
        <div className="input-group" style={{ maxWidth: width }}>
          {field.short_label ? <span className="input-group-text">{field.short_label}</span> : null}
          {children}
          {field.unit ? <span className="input-group-text">{field.unit}</span> : null}
        </div>
      ) : (
        children
      )}
      {field.help && (presentation.helpDisplay === "text" || presentation.helpDisplay === "both") ? (
        <div className="form-text">{field.help}</div>
      ) : null}
    </div>
  );
}

function FieldControl({
  field,
  value,
  onChange,
  disabled,
  readOnly,
  presentation,
}: {
  field: DomainConfigField;
  value: unknown;
  onChange: (next: unknown) => void;
  disabled: boolean;
  readOnly: boolean;
  presentation: Presentation;
}) {
  const id = `domain-field-${field.key.replace(/\./g, "-")}`;
  const locked = readOnly || disabled;
  const tooltip = fieldTooltip(field, presentation);
  const helpAsText = presentation.helpDisplay === "text" || presentation.helpDisplay === "both";

  if (field.type === "boolean") {
    const checked = Boolean(value);
    const hasSegments = Boolean(field.false_label || field.true_label);
    if (hasSegments) {
      return (
        <div
          className="d-flex flex-column gap-2 rounded-3 border bg-body-tertiary px-3 py-2"
          title={tooltip}
          style={{ cursor: tooltip ? "help" : undefined }}
        >
          {presentation.labelDisplay === "visible" && field.label ? (
            <div className="small text-muted">{field.label}</div>
          ) : null}
          <div className="btn-group" role="group" aria-label={field.label || field.key}>
            <button
              type="button"
              className={`btn btn-sm ${!checked ? "btn-primary" : "btn-outline-secondary"}`}
              disabled={locked}
              onClick={() => onChange(false)}
            >
              {field.false_label || "Off"}
            </button>
            <button
              type="button"
              className={`btn btn-sm ${checked ? "btn-primary" : "btn-outline-secondary"}`}
              disabled={locked}
              onClick={() => onChange(true)}
            >
              {field.true_label || "On"}
            </button>
          </div>
          {field.help && helpAsText ? <div className="form-text mb-0">{field.help}</div> : null}
        </div>
      );
    }
    return (
      <div title={tooltip} style={{ cursor: tooltip ? "help" : undefined }}>
        <div className="form-check form-switch">
          <input
            id={id}
            className="form-check-input"
            type="checkbox"
            role="switch"
            checked={checked}
            disabled={locked}
            onChange={(e) => onChange(e.target.checked)}
          />
          <label className="form-check-label" htmlFor={id}>
            {field.label || field.key}
          </label>
        </div>
        {field.help && helpAsText ? <div className="form-text">{field.help}</div> : null}
      </div>
    );
  }

  if (locked && (field.type === "number" || field.type === "string" || field.read_only)) {
    return (
      <ControlShell field={field} htmlFor={id} presentation={presentation}>
        <span className="form-control bg-body-secondary" id={id} aria-readonly="true">
          {formatDisplayValue(value)}
        </span>
      </ControlShell>
    );
  }

  if (field.type === "select") {
    const select = (
      <select
        id={id}
        className="form-select"
        style={field.short_label || field.unit ? undefined : { maxWidth: "280px" }}
        value={value == null ? "" : String(value)}
        disabled={locked}
        onChange={(e) => onChange(e.target.value)}
      >
        {(field.options || []).map((opt) => (
          <option key={String(opt.value)} value={String(opt.value)}>
            {opt.label}
          </option>
        ))}
      </select>
    );
    return (
      <ControlShell field={field} htmlFor={id} presentation={presentation} grow>
        {select}
      </ControlShell>
    );
  }

  if (field.type === "number") {
    const numeric = typeof value === "number" ? value : value == null ? "" : String(value);
    const input = (
      <input
        id={id}
        type="number"
        className="form-control"
        style={field.short_label || field.unit ? undefined : { maxWidth: "180px" }}
        min={field.min}
        max={field.max}
        step={field.step ?? "any"}
        value={numeric}
        disabled={locked}
        onChange={(e) => onChange(parseNumberInput(e.target.value, value))}
      />
    );
    return (
      <ControlShell field={field} htmlFor={id} presentation={presentation}>
        {input}
      </ControlShell>
    );
  }

  return (
    <ControlShell field={field} htmlFor={id} presentation={presentation} grow>
      <input
        id={id}
        type="text"
        className="form-control"
        value={value == null ? "" : String(value)}
        disabled={locked}
        onChange={(e) => onChange(e.target.value)}
      />
    </ControlShell>
  );
}

function NestedFields({
  fields,
  values,
  onChange,
  disabled,
  presentation,
  prefix = "",
}: {
  fields: DomainConfigField[];
  values: Record<string, unknown>;
  onChange: (path: string, value: unknown) => void;
  disabled: boolean;
  presentation: Presentation;
  prefix?: string;
}) {
  return (
    <div className="row g-2">
      {fields.map((field) => {
        const path = prefix ? `${prefix}.${field.key}` : field.key;
        if (!isFieldVisible(field, values)) return null;
        const col = Math.min(12, Math.max(1, Number(field.columns) || 12));
        const readOnly = isFieldReadOnly(field, values);
        const bounds = resolveNumericBounds(field, values);
        const fieldPres = fieldPresentation(field, presentation);
        const resolved: DomainConfigField = {
          ...field,
          key: path,
          min: bounds.min,
          max: bounds.max,
        };
        if (field.type === "object" && Array.isArray(field.fields)) {
          return (
            <div key={path} className={`col-md-${col} mb-2`}>
              {fieldPres.labelDisplay === "visible" && field.label ? (
                <div className="fw-semibold small mb-2">{field.label}</div>
              ) : null}
              <NestedFields
                fields={field.fields}
                values={values}
                onChange={onChange}
                disabled={disabled}
                presentation={fieldPres}
                prefix={path}
              />
            </div>
          );
        }
        if (field.type === "array") {
          const arr = Array.isArray(getByPath(values, path)) ? (getByPath(values, path) as unknown[]) : [];
          return (
            <div key={path} className={`col-md-${col} mb-2`} title={fieldTooltip(field, fieldPres)}>
              {fieldPres.labelDisplay === "visible" && field.label ? (
                <div className="form-label">{field.label}</div>
              ) : null}
              <pre className="small bg-light p-2 rounded mb-0">{JSON.stringify(arr, null, 2)}</pre>
            </div>
          );
        }
        return (
          <div key={path} className={`col-md-${col} mb-2`}>
            <FieldControl
              field={resolved}
              value={getByPath(values, path)}
              onChange={(next) => onChange(path, next)}
              disabled={disabled}
              readOnly={readOnly}
              presentation={fieldPres}
            />
          </div>
        );
      })}
    </div>
  );
}

function validateLocal(fields: DomainConfigField[], values: Record<string, unknown>, prefix = ""): string | null {
  for (const field of fields) {
    const path = prefix ? `${prefix}.${field.key}` : field.key;
    if (field.depends_on && !conditionMatches(field.depends_on, values)) continue;
    if (isFieldReadOnly(field, values)) continue;
    if (field.type === "object" && field.fields) {
      const nested = validateLocal(field.fields, values, path);
      if (nested) return nested;
      continue;
    }
    if (field.type !== "number") continue;
    const raw = getByPath(values, path);
    if (raw === "" || raw == null) continue;
    const n = Number(raw);
    const bounds = resolveNumericBounds(field, values);
    if (!Number.isFinite(n)) return field.label || field.key;
    if (bounds.min != null && n < bounds.min) return field.label || field.key;
    if (bounds.max != null && n > bounds.max) return field.label || field.key;
  }
  return null;
}

export function DomainConfigSlot({
  machineName,
  schema,
  config,
  machineState,
  onConfigUpdated,
  onSchemaUpdated,
}: DomainConfigSlotProps) {
  const { t } = useTranslation();
  const [values, setValues] = useState<Record<string, unknown>>(config || {});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setValues(config || {});
  }, [machineName, config]);

  const sections = schema.sections || [];
  const unsupported = Number(schema.version || 1) > SCHEMA_VERSION_SUPPORTED;
  const title = schema.title || t("machines.domainConfigTitle");
  const rootPresentation = schemaPresentation(schema);

  const allFields = useMemo(
    () => sections.flatMap((section) => section.fields || []),
    [sections]
  );

  useEffect(() => {
    if (!machineState) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const domain = await getMachineDomainConfig(machineName);
        if (cancelled || !domain?.config) return;
        const next = domain.config as Record<string, unknown>;
        const applyKeys = [
          "_apply_status",
          "_apply_message",
          "_buffer_filled",
          "_buffer_need",
          "_sm_state",
          "_warnings",
        ];
        setValues((prev) => {
          const merged = { ...prev };
          for (const key of applyKeys) {
            if (key in next) merged[key] = next[key];
            else delete merged[key];
          }
          return merged;
        });
        if (domain.schema) onSchemaUpdated?.(domain.schema);
      } catch {
        /* keep the local form */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [machineName, machineState]);

  const handleChange = (path: string, value: unknown) => {
    setValues((prev) => applyDwtConstraints(allFields, setByPath(prev, path, value)));
  };

  const applyServerState = async (fallbackConfig: Record<string, unknown>) => {
    try {
      const domain = await getMachineDomainConfig(machineName);
      if (domain?.config) {
        setValues(domain.config);
        onConfigUpdated?.(domain.config);
      } else {
        setValues(fallbackConfig);
        onConfigUpdated?.(fallbackConfig);
      }
      if (domain?.schema) {
        onSchemaUpdated?.(domain.schema);
      }
    } catch {
      setValues(fallbackConfig);
      onConfigUpdated?.(fallbackConfig);
    }
  };

  const handleSave = async () => {
    const invalid = validateLocal(allFields, values);
    if (invalid) {
      showToast(t("machines.domainConfigValidationError"), "error");
      return;
    }
    setSaving(true);
    try {
      const { _reset: _ignoredReset, _set_factory: _ignoredFactory, ...payload } = values;
      const result = await putMachineDomainConfig(machineName, payload);
      const next = result.config || values;
      await applyServerState(next);
      showToast(t("machines.domainConfigSaved"), "success");
    } catch (err: any) {
      const data = err?.response?.data;
      const message =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        err?.message ??
        t("machines.domainConfigSaveError");
      showToast(message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    const defaults = schema.ui_hints?.factory_defaults;
    if (!defaults || Object.keys(defaults).length === 0) {
      showToast(t("machines.domainConfigSaveError"), "error");
      return;
    }
    setSaving(true);
    try {
      const result = await putMachineDomainConfig(machineName, { _reset: true });
      const next = result.config || { ...values, ...defaults };
      await applyServerState(next);
      showToast(t("machines.domainConfigResetSaved"), "success");
    } catch (err: any) {
      const data = err?.response?.data;
      const message =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        err?.message ??
        t("machines.domainConfigSaveError");
      showToast(message, "error");
    } finally {
      setSaving(false);
    }
  };

  const handleSetFactory = async () => {
    const invalid = validateLocal(allFields, values);
    if (invalid) {
      showToast(t("machines.domainConfigValidationError"), "error");
      return;
    }
    setSaving(true);
    try {
      const { _reset: _ignoredReset, _set_factory: _ignoredFactory, ...payload } = values;
      const result = await putMachineDomainConfig(machineName, { ...payload, _set_factory: true });
      const next = result.config || values;
      await applyServerState(next);
      showToast(t("machines.domainConfigSetFactorySaved"), "success");
    } catch (err: any) {
      const data = err?.response?.data;
      const message =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        err?.message ??
        t("machines.domainConfigSaveError");
      showToast(message, "error");
    } finally {
      setSaving(false);
    }
  };

  if (!sections.length) return null;

  const hasFactoryDefaults = Boolean(
    schema.ui_hints?.factory_defaults && Object.keys(schema.ui_hints.factory_defaults).length
  );
  const showSetFactory = schema.ui_hints?.show_set_factory !== false && hasFactoryDefaults;
  const factoryDefaults = (schema.ui_hints?.factory_defaults || {}) as Record<string, unknown>;
  const comparableKeys = visibleEditableKeys(allFields, values);
  const factoryKeys = comparableKeys.filter((key) => Object.prototype.hasOwnProperty.call(factoryDefaults, key));
  const isDirtyVsSaved = valuesDiffer(values, config || {}, comparableKeys);
  const differsFromFactory = hasFactoryDefaults && valuesDiffer(values, factoryDefaults, factoryKeys);
  const canSave = isDirtyVsSaved;
  const canRestoreFactory = differsFromFactory;
  const canSetFactory = differsFromFactory;

  return (
    <Card title={title} className="mt-3">
      {unsupported ? (
        <div className="alert alert-warning py-2" role="alert">
          {t("machines.domainConfigUnsupportedVersion")}
        </div>
      ) : null}
      {typeof values._apply_message === "string" && values._apply_message ? (
        <div className={applyBannerClass(values._apply_status)} role="status">
          {values._apply_message}
        </div>
      ) : null}
      {warningList(values._warnings).map((warning) => (
        <div key={warning} className="alert alert-warning py-2 small mb-3" role="status">
          {warning}
        </div>
      ))}
      <fieldset disabled={saving}>
        {sections.map((section, index) => {
          if (section.depends_on?.field) {
            if (!conditionMatches(section.depends_on, values)) {
              return null;
            }
          }
          const sectionPres = sectionPresentation(section, rootPresentation);
          return (
            <div key={section.id || `section-${index}`} className="mb-3">
              {section.label ? <h6 className="mb-3">{section.label}</h6> : null}
              {section.hint ? (
                <div className="alert alert-info py-2 small mb-3" role="status">
                  {section.hint}
                </div>
              ) : null}
              {(section.fields || []).length ? (
                <NestedFields
                  fields={section.fields || []}
                  values={values}
                  onChange={handleChange}
                  disabled={saving}
                  presentation={sectionPres}
                />
              ) : null}
            </div>
          );
        })}
      </fieldset>
      <div className="d-flex justify-content-between flex-wrap gap-2">
        <div className="d-flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            loading={saving}
            disabled={saving || !canRestoreFactory}
            onClick={handleReset}
          >
            {t("machines.domainConfigReset")}
          </Button>
          {showSetFactory ? (
            <Button
              type="button"
              variant="secondary"
              loading={saving}
              disabled={saving || !canSetFactory}
              onClick={handleSetFactory}
            >
              {t("machines.domainConfigSetFactory")}
            </Button>
          ) : null}
        </div>
        <Button type="button" variant="primary" loading={saving} disabled={saving || !canSave} onClick={handleSave}>
          {t("machines.domainConfigSave")}
        </Button>
      </div>
    </Card>
  );
}
