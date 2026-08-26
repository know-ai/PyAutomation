import { useEffect, useMemo, useState } from "react";
import { Card } from "./Card";
import { Button } from "./Button";
import { useTranslation } from "../hooks/useTranslation";
import { showToast } from "../utils/toast";
import {
  putMachineDomainConfig,
  type DomainConfigField,
  type DomainUiSchema,
} from "../services/machines";

const SCHEMA_VERSION_SUPPORTED = 1;

type DomainConfigSlotProps = {
  machineName: string;
  schema: DomainUiSchema;
  config: Record<string, unknown>;
  onConfigUpdated?: (config: Record<string, unknown>) => void;
};

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

function isFieldVisible(field: DomainConfigField, values: Record<string, unknown>): boolean {
  const dep = field.depends_on;
  if (!dep?.field) return true;
  const current = getByPath(values, dep.field);
  if ("equals" in dep) return current === dep.equals;
  return Boolean(current);
}

function parseNumberInput(raw: string, fallback: unknown): unknown {
  if (raw === "" || raw === "-") return raw;
  const n = Number(raw);
  return Number.isFinite(n) ? n : fallback;
}

function FieldControl({
  field,
  value,
  onChange,
  disabled,
}: {
  field: DomainConfigField;
  value: unknown;
  onChange: (next: unknown) => void;
  disabled: boolean;
}) {
  const id = `domain-field-${field.key.replace(/\./g, "-")}`;
  const readOnly = Boolean(field.read_only) || disabled;

  if (field.type === "boolean") {
    return (
      <div className="form-check">
        <input
          id={id}
          className="form-check-input"
          type="checkbox"
          checked={Boolean(value)}
          disabled={readOnly}
          onChange={(e) => onChange(e.target.checked)}
        />
        <label className="form-check-label" htmlFor={id}>
          {field.label || field.key}
        </label>
      </div>
    );
  }

  if (field.type === "select") {
    return (
      <select
        id={id}
        className="form-select"
        style={{ maxWidth: "280px" }}
        value={value == null ? "" : String(value)}
        disabled={readOnly}
        onChange={(e) => onChange(e.target.value)}
      >
        {(field.options || []).map((opt) => (
          <option key={String(opt.value)} value={String(opt.value)}>
            {opt.label}
          </option>
        ))}
      </select>
    );
  }

  if (field.type === "number") {
    const numeric = typeof value === "number" ? value : value == null ? "" : String(value);
    return (
      <div className="d-flex align-items-center gap-2">
        <input
          id={id}
          type="number"
          className="form-control"
          style={{ maxWidth: "180px" }}
          min={field.min}
          max={field.max}
          step={field.step ?? "any"}
          value={numeric}
          disabled={readOnly}
          onChange={(e) => onChange(parseNumberInput(e.target.value, value))}
        />
        {field.unit ? <span className="text-muted small">{field.unit}</span> : null}
      </div>
    );
  }

  return (
    <input
      id={id}
      type="text"
      className="form-control"
      style={{ maxWidth: "320px" }}
      value={value == null ? "" : String(value)}
      disabled={readOnly}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function NestedFields({
  fields,
  values,
  onChange,
  disabled,
  prefix = "",
}: {
  fields: DomainConfigField[];
  values: Record<string, unknown>;
  onChange: (path: string, value: unknown) => void;
  disabled: boolean;
  prefix?: string;
}) {
  return (
    <>
      {fields.map((field) => {
        const path = prefix ? `${prefix}.${field.key}` : field.key;
        const resolved: DomainConfigField = { ...field, key: path };
        if (!isFieldVisible(field, values)) return null;
        if (field.type === "object" && Array.isArray(field.fields)) {
          return (
            <div key={path} className="mb-3">
              <div className="fw-semibold small mb-2">{field.label || field.key}</div>
              <div className="ps-3 border-start">
                <NestedFields
                  fields={field.fields}
                  values={values}
                  onChange={onChange}
                  disabled={disabled}
                  prefix={path}
                />
              </div>
            </div>
          );
        }
        if (field.type === "array") {
          const arr = Array.isArray(getByPath(values, path)) ? (getByPath(values, path) as unknown[]) : [];
          return (
            <div key={path} className="mb-3">
              <label className="form-label">{field.label || field.key}</label>
              <pre className="small bg-light p-2 rounded mb-0">{JSON.stringify(arr, null, 2)}</pre>
            </div>
          );
        }
        return (
          <div key={path} className="mb-3">
            {field.type !== "boolean" ? (
              <label className="form-label d-block" htmlFor={`domain-field-${path.replace(/\./g, "-")}`}>
                {field.label || field.key}
              </label>
            ) : null}
            <FieldControl
              field={resolved}
              value={getByPath(values, path)}
              onChange={(next) => onChange(path, next)}
              disabled={disabled}
            />
            {field.help ? <div className="form-text">{field.help}</div> : null}
          </div>
        );
      })}
    </>
  );
}

function validateLocal(fields: DomainConfigField[], values: Record<string, unknown>, prefix = ""): string | null {
  for (const field of fields) {
    const path = prefix ? `${prefix}.${field.key}` : field.key;
    if (field.depends_on) {
      const current = getByPath(values, field.depends_on.field);
      if ("equals" in field.depends_on && current !== field.depends_on.equals) continue;
    }
    if (field.type === "object" && field.fields) {
      const nested = validateLocal(field.fields, values, path);
      if (nested) return nested;
      continue;
    }
    if (field.type !== "number") continue;
    const raw = getByPath(values, path);
    if (raw === "" || raw == null) continue;
    const n = Number(raw);
    if (!Number.isFinite(n)) return field.label || field.key;
    if (field.min != null && n < field.min) return field.label || field.key;
    if (field.max != null && n > field.max) return field.label || field.key;
  }
  return null;
}

export function DomainConfigSlot({ machineName, schema, config, onConfigUpdated }: DomainConfigSlotProps) {
  const { t } = useTranslation();
  const [values, setValues] = useState<Record<string, unknown>>(config || {});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setValues(config || {});
  }, [machineName, config]);

  const sections = schema.sections || [];
  const unsupported = Number(schema.version || 1) > SCHEMA_VERSION_SUPPORTED;
  const title = schema.title || t("machines.domainConfigTitle");

  const allFields = useMemo(
    () => sections.flatMap((section) => section.fields || []),
    [sections]
  );

  const handleChange = (path: string, value: unknown) => {
    setValues((prev) => setByPath(prev, path, value));
  };

  const handleSave = async () => {
    const invalid = validateLocal(allFields, values);
    if (invalid) {
      showToast(t("machines.domainConfigValidationError"), "error");
      return;
    }
    setSaving(true);
    try {
      const result = await putMachineDomainConfig(machineName, values);
      const next = result.config || values;
      setValues(next);
      onConfigUpdated?.(next);
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

  if (!sections.length) return null;

  return (
    <Card title={title} className="mt-3">
      {unsupported ? (
        <div className="alert alert-warning py-2" role="alert">
          {t("machines.domainConfigUnsupportedVersion")}
        </div>
      ) : null}
      <fieldset disabled={saving}>
        {sections.map((section, index) => (
          <div key={section.id || `section-${index}`} className="mb-3">
            {section.label ? <h6 className="mb-3">{section.label}</h6> : null}
            <NestedFields
              fields={section.fields || []}
              values={values}
              onChange={handleChange}
              disabled={saving}
            />
          </div>
        ))}
      </fieldset>
      <div className="d-flex justify-content-end">
        <Button type="button" variant="primary" loading={saving} onClick={handleSave}>
          {t("machines.domainConfigSave")}
        </Button>
      </div>
    </Card>
  );
}
