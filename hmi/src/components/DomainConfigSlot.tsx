import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Card } from "./Card";
import { Button } from "./Button";
import { OpsConfirmModal } from "./OpsConfirmModal";
import { useTranslation } from "../hooks/useTranslation";
import { showToast } from "../utils/toast";
import {
  getMachineDomainConfig,
  postMachineDomainFiles,
  putMachineDomainConfig,
  type DomainConfigField,
  type DomainConfigSection,
  type DomainHelpDisplay,
  type DomainLabelDisplay,
  type DomainUiSchema,
} from "../services/machines";
import { beginProcessRestart } from "../services/processRestart";

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
  if (
    status === "pending" ||
    status === "restarting" ||
    status === "pending_restart" ||
    status === "blocked" ||
    status === "filling" ||
    status === "rearm"
  ) {
    return "alert alert-warning py-2 small mb-3";
  }
  return "alert alert-info py-2 small mb-3";
}

function sectionCardClass(tone: unknown): string {
  if (tone === "warning") return "card mb-3 border-warning";
  if (tone === "success") return "card mb-3 border-success";
  return "card mb-3";
}

function sectionHeaderClass(tone: unknown, extra = "py-2"): string {
  if (tone === "warning") return `card-header ${extra} bg-warning-subtle`;
  if (tone === "success") return `card-header ${extra} bg-success-subtle`;
  return `card-header ${extra}`;
}

function sectionHintClass(tone: unknown): string {
  if (tone === "warning") return "alert alert-warning py-2 small mb-3";
  if (tone === "success") return "alert alert-success py-2 small mb-3";
  return "alert alert-info py-2 small mb-3";
}

function isIncompleteSave(saved: Record<string, unknown>): boolean {
  const missingMaps = Array.isArray(saved._missing_input_mappings) ? saved._missing_input_mappings : [];
  const missingTags = Array.isArray(saved._missing_field_attrs) ? saved._missing_field_attrs : [];
  return missingMaps.length > 0 || missingTags.length > 0 || saved._apply_status === "blocked";
}

const INTERNAL_COMPARE_KEYS = new Set([
  "_reset",
  "_set_factory",
  "_warnings",
  "_apply_status",
  "_apply_message",
  "_restart_available",
  "_restart_eta_s",
  "_buffer_filled",
  "_buffer_need",
  "_sm_state",
  "_effective_pressure_mode",
  "_pressure_tags_status",
  "_missing_tags_message",
  "_show_inputs_mapping",
  "_inputs_mapping_complete",
  "_missing_input_mappings",
  "_missing_field_attrs",
]);

function normalizeCompareValue(value: unknown): string {
  if (typeof value === "boolean") return value ? "1" : "0";
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (value == null || value === "") return "";
  if (Array.isArray(value) || (typeof value === "object" && value !== null)) {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  const asNumber = Number(value);
  if (value !== "" && Number.isFinite(asNumber) && String(value).trim() !== "") {
    return String(asNumber);
  }
  return String(value);
}

function visibleEditableKeys(
  fields: DomainConfigField[],
  values: Record<string, unknown>,
  prefix = ""
): string[] {
  const keys: string[] = [];
  for (const field of fields) {
    const path = prefix ? `${prefix}.${field.key}` : field.key;
    if (!isFieldVisible(field, values)) continue;
    if (field.read_only || isFieldReadOnly(field, values)) continue;
    if (field.type === "files") continue;
    if (field.type === "object" && field.fields) {
      keys.push(...visibleEditableKeys(field.fields, values, path));
      continue;
    }
    keys.push(path);
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
    if (normalizeCompareValue(getByPath(left, key)) !== normalizeCompareValue(getByPath(right, key))) {
      return true;
    }
  }
  return false;
}

function selectOptions(field: DomainConfigField): Array<{ value: string; label: string }> {
  return (field.options || []).map((opt) =>
    typeof opt === "string" ? { value: opt, label: opt } : { value: String(opt.value), label: opt.label }
  );
}

function itemFields(field: DomainConfigField): DomainConfigField[] {
  if (Array.isArray(field.items?.fields) && field.items.fields.length) {
    return field.items.fields;
  }
  const properties = field.items?.properties;
  if (properties && typeof properties === "object") {
    return Object.entries(properties).map(([key, spec]) => ({
      key,
      type: "string",
      ...(spec as DomainConfigField),
    }));
  }
  return [];
}

function emptyItem(fields: DomainConfigField[]): Record<string, unknown> {
  const row: Record<string, unknown> = {};
  for (const field of fields) {
    if (field.type === "number") row[field.key] = field.min ?? 0;
    else if (field.type === "boolean") row[field.key] = false;
    else if (field.type === "select") {
      const opts = selectOptions(field);
      row[field.key] = opts[0]?.value ?? "";
    } else row[field.key] = "";
  }
  return row;
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

function selectMaxWidth(field: DomainConfigField): string {
  const col = Number(field.columns) || 12;
  if (col <= 4) return "9.25rem";
  if (col < 12) return "11rem";
  return "16rem";
}

function ControlShell({
  field,
  htmlFor,
  presentation,
  children,
  grow,
  forceLabel,
}: {
  field: DomainConfigField;
  htmlFor?: string;
  presentation: Presentation;
  children: ReactNode;
  grow?: boolean;
  forceLabel?: boolean;
}) {
  const tooltip = fieldTooltip(field, presentation);
  const showLabel =
    Boolean(field.label) &&
    presentation.labelDisplay === "visible" &&
    (forceLabel || field.type !== "boolean");
  const width = grow ? "100%" : field.type === "select" ? selectMaxWidth(field) : "220px";
  return (
    <div title={tooltip} style={{ cursor: tooltip ? "help" : undefined }}>
      {field.label ? (
        <label className={showLabel ? "form-label d-block small mb-1" : "visually-hidden"} htmlFor={htmlFor}>
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
    const compact = Number(field.columns) > 0 && Number(field.columns) < 12;
    if (hasSegments && compact) {
      return (
        <ControlShell field={field} htmlFor={id} presentation={presentation} forceLabel>
          <div className="btn-group" role="group" aria-label={field.label || field.key}>
            <button
              type="button"
              className={`btn btn-sm py-0 px-2 ${!checked ? "btn-primary" : "btn-outline-secondary"}`}
              style={{ minHeight: "31px" }}
              disabled={locked}
              onClick={() => onChange(false)}
            >
              {field.false_label || "Off"}
            </button>
            <button
              type="button"
              className={`btn btn-sm py-0 px-2 ${checked ? "btn-primary" : "btn-outline-secondary"}`}
              style={{ minHeight: "31px" }}
              disabled={locked}
              onClick={() => onChange(true)}
            >
              {field.true_label || "On"}
            </button>
          </div>
        </ControlShell>
      );
    }
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
    const compact = Number(field.columns) > 0 && Number(field.columns) < 12;
    const select = (
      <select
        id={id}
        className="form-select form-select-sm"
        style={
          field.short_label || field.unit
            ? undefined
            : compact
              ? { maxWidth: selectMaxWidth(field), width: "auto" }
              : { maxWidth: "16rem" }
        }
        value={value == null ? "" : String(value)}
        disabled={locked}
        onChange={(e) => onChange(e.target.value)}
      >
        {(selectOptions(field) || []).map((opt) => (
          <option key={String(opt.value)} value={String(opt.value)}>
            {opt.label}
          </option>
        ))}
      </select>
    );
    return (
      <ControlShell field={field} htmlFor={id} presentation={presentation} grow={!compact}>
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

function ArrayTableEditor({
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
  const { t } = useTranslation();
  const columns = itemFields(field);
  const rows = Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
  const locked = disabled || readOnly;
  const updateRow = (index: number, key: string, next: unknown) => {
    const copy = rows.map((row) => ({ ...(row || {}) }));
    copy[index] = { ...(copy[index] || {}), [key]: next };
    onChange(copy);
  };
  const addRow = () => onChange([...rows, emptyItem(columns)]);
  const removeRow = (index: number) => onChange(rows.filter((_, i) => i !== index));
  return (
    <div title={fieldTooltip(field, presentation)}>
      {presentation.labelDisplay === "visible" && field.label ? (
        <div className="form-label">{field.label}</div>
      ) : null}
      <div className="table-responsive">
        <table className="table table-sm align-middle mb-2">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.key} className="small fw-semibold">
                  {col.label || col.key}
                  {col.unit ? ` (${col.unit})` : ""}
                </th>
              ))}
              {!locked ? <th className="small fw-semibold" /> : null}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length + (locked ? 0 : 1)} className="text-muted small">
                  —
                </td>
              </tr>
            ) : (
              rows.map((row, index) => (
                <tr key={`${field.key}-${index}`}>
                  {columns.map((col) => (
                    <td key={col.key}>
                      <FieldControl
                        field={{ ...col, label: undefined, help: col.help, unit: undefined }}
                        value={row?.[col.key]}
                        onChange={(next) => updateRow(index, col.key, next)}
                        disabled={locked}
                        readOnly={locked}
                        presentation={{ ...presentation, labelDisplay: "hidden", helpDisplay: "tooltip" }}
                      />
                    </td>
                  ))}
                  {!locked ? (
                    <td className="text-end" style={{ width: 1 }}>
                      <button
                        type="button"
                        className="btn btn-outline-danger btn-sm"
                        onClick={() => removeRow(index)}
                      >
                        {t("machines.domainConfigRemoveRow")}
                      </button>
                    </td>
                  ) : null}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {!locked ? (
        <button type="button" className="btn btn-outline-secondary btn-sm" onClick={addRow}>
          {t("machines.domainConfigAddRow")}
        </button>
      ) : null}
      {field.help && (presentation.helpDisplay === "text" || presentation.helpDisplay === "both") ? (
        <div className="form-text">{field.help}</div>
      ) : null}
    </div>
  );
}

type ArtifactStatus = {
  path?: string;
  files?: string[];
  missing?: string[];
  ready?: boolean;
};

function artifactStatus(value: unknown): ArtifactStatus {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value as ArtifactStatus;
}

const PFM_BINARY_PREFIXES: number[][] = [
  [0x25, 0x50, 0x44, 0x46],
  [0x50, 0x4b, 0x03, 0x04],
  [0x50, 0x4b, 0x05, 0x06],
  [0x50, 0x4b, 0x07, 0x08],
  [0xd0, 0xcf, 0x11, 0xe0],
  [0x89, 0x50, 0x4e, 0x47],
  [0xff, 0xd8, 0xff],
  [0x47, 0x49, 0x46, 0x38],
];

function bytesStartWith(bytes: Uint8Array, prefix: number[]): boolean {
  return prefix.every((value, index) => bytes[index] === value);
}

function artifactFileName(file: File): string {
  const raw = String(file.name || "").replace(/\\/g, "/");
  const slash = raw.lastIndexOf("/");
  return (slash >= 0 ? raw.slice(slash + 1) : raw).trim();
}

async function peekPfmArtifactError(
  file: File,
  fileName?: string,
  slot?: { engine?: string; role?: string }
): Promise<string | null> {
  const name = fileName || artifactFileName(file);
  const head = new Uint8Array(await file.slice(0, 16).arrayBuffer());
  if (PFM_BINARY_PREFIXES.some((prefix) => bytesStartWith(head, prefix))) {
    return "parece un PDF, Office u otro binario";
  }
  const sample = await file.slice(0, 8000).text();
  const trimmed = sample.replace(/^\uFEFF/, "").trimStart();
  if (name === "model_lgbm.txt") {
    const first = (trimmed.split(/\r?\n/, 1)[0] || "").trim().toLowerCase();
    if (first === "tree" || trimmed.startsWith("{")) return null;
    return "no es un modelo LightGBM (debe empezar por 'tree')";
  }
  if (name.endsWith(".json")) {
    let data: unknown;
    try {
      data = JSON.parse(await file.text());
    } catch {
      return "no es JSON válido";
    }
    if (name === "features_schema.json") {
      if (!Array.isArray(data) || !data.length || data.some((item) => typeof item !== "string" || !item.trim())) {
        return "debe ser un array de nombres de features";
      }
      return null;
    }
    if (name.startsWith("lgbm_inference_config")) {
      const obj = data && typeof data === "object" && !Array.isArray(data) ? (data as Record<string, unknown>) : null;
      if (!obj) return "debe ser un objeto JSON";
      if (!Array.isArray(obj.inputs) || !obj.inputs.length) return "falta 'inputs'";
      if (!Array.isArray(obj.feature_columns) || !obj.feature_columns.length) return "falta 'feature_columns'";
      if (!(Number(obj.window_size) >= 1)) return "'window_size' debe ser ≥ 1";
      return inferenceConfigRoleError(obj, slot);
    }
    if (name === "label_mapping.json") {
      const obj = data && typeof data === "object" && !Array.isArray(data) ? (data as Record<string, unknown>) : null;
      if (!obj) return "debe ser un objeto JSON";
      if (!("labels" in obj || "cluster_centers" in obj || "mapping" in obj || "classes" in obj || "label_to_index" in obj)) {
        return "no parece un label_mapping (labels/cluster_centers/mapping)";
      }
      return null;
    }
  }
  return null;
}

const INFERENCE_SLOT_LABEL: Record<string, string> = {
  "PFM:DETECTION": "PFM / Detección (clasificación binaria)",
  "PFM:LEAKFLOW": "PFM / Caudal de fuga (regresión)",
  "PFM:SIZE": "PFM / Tamaño de fuga (clasificación)",
  "PFM:LOCATION": "PFM / Localización (clasificación)",
  "OBSERVER:DETECTION": "Observer / Detección (regresión de caudal)",
  "OBSERVER:SIZE": "Observer / Tamaño de fuga (regresión)",
  "OBSERVER:LOCATION": "Observer / Localización (regresión)",
};

function inferenceConfigRoleError(
  obj: Record<string, unknown>,
  slot?: { engine?: string; role?: string }
): string | null {
  const engine = String(slot?.engine || "").toUpperCase();
  const role = String(slot?.role || "").toUpperCase();
  if (!engine || !role) return null;
  const key = `${engine}:${role}`;
  const label = INFERENCE_SLOT_LABEL[key] || `${engine} / ${role}`;
  const problem = String(obj.problem_type || "").trim().toLowerCase();
  const labelCol = String(obj.label_column || "").trim().toUpperCase();
  const output = String(obj.output_key || "").trim().toLowerCase();
  const expectedProblem: Record<string, string> = {
    "PFM:DETECTION": "binary",
    "PFM:LEAKFLOW": "regression",
    "PFM:SIZE": "multiclass",
    "PFM:LOCATION": "multiclass",
    "OBSERVER:DETECTION": "regression",
    "OBSERVER:SIZE": "regression",
    "OBSERVER:LOCATION": "regression",
  };
  const want = expectedProblem[key];
  if (!want) return null;
  if (!problem) {
    return `falta problem_type; el slot ${label} espera ${want}`;
  }
  if (problem !== want) {
    return `es '${problem}', pero ${label} espera ${want}. No mezcle detección/diagnóstico ni PFM/Observer`;
  }
  const needNeedle: Record<string, string> = {
    "PFM:DETECTION": "LABEL",
    "PFM:LEAKFLOW": "LEAK_FLOW",
    "PFM:SIZE": "LEAK_SIZE",
    "PFM:LOCATION": "LEAK_LOCATION",
    "OBSERVER:DETECTION": "LEAK_FLOW",
    "OBSERVER:SIZE": "LEAK_SIZE",
    "OBSERVER:LOCATION": "LEAK_LOCATION",
  };
  const forbid: Record<string, string[]> = {
    "PFM:DETECTION": ["LEAK_FLOW", "LEAK_SIZE", "LEAK_LOCATION"],
    "PFM:LEAKFLOW": ["LEAK_SIZE", "LEAK_LOCATION"],
    "PFM:SIZE": ["LEAK_LOCATION", "LEAK_FLOW"],
    "PFM:LOCATION": ["LEAK_SIZE", "LEAK_FLOW"],
    "OBSERVER:DETECTION": ["LEAK_SIZE", "LEAK_LOCATION"],
    "OBSERVER:SIZE": ["LEAK_LOCATION", "LEAK_FLOW"],
    "OBSERVER:LOCATION": ["LEAK_SIZE", "LEAK_FLOW"],
  };
  const needle = needNeedle[key];
  if (needle === "LABEL") {
    if (labelCol && (labelCol.includes("LEAK_FLOW") || labelCol.includes("LEAK_SIZE") || labelCol.includes("LEAK_LOCATION"))) {
      return `label_column='${obj.label_column}' no es de ${label}`;
    }
  } else if (needle && !labelCol.includes(needle)) {
    return `label_column='${obj.label_column || ""}' no corresponde a ${label}`;
  }
  for (const token of forbid[key] || []) {
    if (needle === "LABEL" && token === "LABEL") continue;
    if (labelCol.includes(token)) {
      return `label_column='${obj.label_column}' corresponde a otro rol. Slot: ${label}`;
    }
  }
  if (key === "OBSERVER:DETECTION" && output !== "leak_flow") {
    return `output_key debe ser 'leak_flow' en ${label} (un PFM LEAKFLOW no sirve aquí)`;
  }
  if (key === "PFM:LEAKFLOW" && output === "leak_flow") {
    return `output_key='leak_flow' es de Observer Detección, no de ${label}`;
  }
  return null;
}

function FilesControl({
  field,
  value,
  pending,
  onPending,
  disabled,
  readOnly,
  presentation,
}: {
  field: DomainConfigField;
  value: unknown;
  pending: File[];
  onPending: (next: File[]) => void;
  disabled: boolean;
  readOnly: boolean;
  presentation: Presentation;
}) {
  const { t } = useTranslation();
  const locked = disabled || readOnly;
  const status = artifactStatus(value);
  const onDisk = status.files || [];
  const required = field.required_names || status.missing || [];
  const path = status.path || "";
  const ready = Boolean(status.ready);
  const pendingNames = pending.map((file) => artifactFileName(file));
  const covered = new Set([...onDisk, ...pendingNames]);
  const stillMissing = required.filter((name) => !covered.has(name));
  const pendingCoversRequired = Boolean(pending.length) && stillMissing.length === 0;
  const id = `domain-files-${field.key.replace(/\./g, "-")}`;
  const allowedNames = new Set(
    [...(field.required_names || []), ...(field.optional_names || [])].filter(Boolean)
  );
  const [validating, setValidating] = useState(false);
  const pendingRef = useRef(pending);
  pendingRef.current = pending;
  const mergeGen = useRef(0);
  const mergeFiles = (list: FileList | null) => {
    if (locked) return;
    const picked = Array.from(list || []);
    if (!picked.length) return;
    const gen = ++mergeGen.current;
    void (async () => {
      const byName = new Map<string, File>();
      for (const file of pendingRef.current) byName.set(artifactFileName(file), file);
      const rejectedNames: string[] = [];
      const rejectedContent: string[] = [];
      setValidating(true);
      try {
        for (const file of picked) {
          const name = artifactFileName(file);
          if (allowedNames.size && !allowedNames.has(name)) {
            rejectedNames.push(name || file.name);
            continue;
          }
          let contentError: string | null = null;
          try {
            contentError = await peekPfmArtifactError(file, name, {
              engine: field.artifact_engine,
              role: field.artifact_role,
            });
          } catch {
            contentError = "no se pudo leer el archivo";
          }
          if (gen !== mergeGen.current) return;
          if (contentError) {
            rejectedContent.push(`${name} (${contentError})`);
            continue;
          }
          byName.set(name, file);
        }
        if (gen !== mergeGen.current) return;
        if (rejectedNames.length) {
          showToast(
            `${t("machines.domainConfigFilesRejected")}: ${rejectedNames.join(", ")}. ${t(
              "machines.domainConfigFilesAllowedNames"
            )}: ${Array.from(allowedNames).join(", ")}`,
            "error"
          );
        }
        if (rejectedContent.length) {
          showToast(`${t("machines.domainConfigFilesBadContent")}: ${rejectedContent.join("; ")}`, "error");
        }
        onPending(Array.from(byName.values()));
      } finally {
        if (gen === mergeGen.current) setValidating(false);
      }
    })();
  };
  const removePending = (name: string) => {
    onPending(pending.filter((file) => artifactFileName(file) !== name));
  };
  return (
    <div title={fieldTooltip(field, presentation)}>
      {presentation.labelDisplay === "visible" && field.label ? (
        <div className="form-label">{field.label}</div>
      ) : null}
      <div className="d-flex flex-wrap align-items-center gap-2 mb-2">
        {ready ? (
          <span className="badge text-bg-success">{t("machines.domainConfigFilesReady")}</span>
        ) : pendingCoversRequired ? (
          <span className="badge text-bg-warning">{t("machines.domainConfigFilesPendingSave")}</span>
        ) : (
          <span className="badge text-bg-secondary">{t("machines.domainConfigFilesEmpty")}</span>
        )}
        {path ? <span className="small text-muted font-monospace">{path}</span> : null}
      </div>
      {onDisk.length ? (
        <div className="small mb-1">
          <span className="text-muted">{t("machines.domainConfigFilesOnDisk")}: </span>
          {onDisk.join(", ")}
        </div>
      ) : null}
      {!ready && stillMissing.length ? (
        <div className="small text-warning mb-1">
          {t("machines.domainConfigFilesMissing")}: {stillMissing.join(", ")}
        </div>
      ) : null}
      {validating ? (
        <div className="small text-muted mb-1">{t("machines.domainConfigFilesValidating")}</div>
      ) : null}
      {pending.length ? (
        <div className="small mb-2">
          <div className="text-muted mb-1">{t("machines.domainConfigFilesSelected")}:</div>
          <ul className="list-unstyled mb-1">
            {pending.map((file) => {
              const name = artifactFileName(file);
              return (
              <li key={name} className="d-flex align-items-center gap-2 mb-1">
                <span className="font-monospace">{name}</span>
                {!locked ? (
                  <button
                    type="button"
                    className="btn btn-link btn-sm p-0"
                    onClick={() => removePending(name)}
                  >
                    {t("machines.domainConfigFilesRemove")}
                  </button>
                ) : null}
              </li>
              );
            })}
          </ul>
          {!locked ? (
            <button type="button" className="btn btn-link btn-sm p-0" onClick={() => onPending([])}>
              {t("machines.domainConfigFilesClear")}
            </button>
          ) : null}
        </div>
      ) : null}
      {pending.length ? (
        <div className="form-text mb-2">
          {ready ? t("machines.domainConfigFilesReplaceHint") : t("machines.domainConfigFilesSaveHint")}
        </div>
      ) : null}
      {!locked ? (
        <input
          id={id}
          type="file"
          className="form-control form-control-sm"
          multiple={field.multiple !== false}
          disabled={locked}
          onChange={(event) => {
            mergeFiles(event.currentTarget.files);
          }}
        />
      ) : null}
      {field.help && (presentation.helpDisplay === "text" || presentation.helpDisplay === "both") ? (
        <div className="form-text">{field.help}</div>
      ) : null}
    </div>
  );
}

function NestedFields({
  fields,
  values,
  onChange,
  disabled,
  presentation,
  prefix = "",
  pendingFiles,
  onPendingFiles,
}: {
  fields: DomainConfigField[];
  values: Record<string, unknown>;
  onChange: (path: string, value: unknown) => void;
  disabled: boolean;
  presentation: Presentation;
  prefix?: string;
  pendingFiles: Record<string, File[]>;
  onPendingFiles: (path: string, files: File[]) => void;
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
                pendingFiles={pendingFiles}
                onPendingFiles={onPendingFiles}
              />
            </div>
          );
        }
        if (field.type === "files") {
          return (
            <div key={path} className={`col-md-${col} mb-2`}>
              <FilesControl
                field={resolved}
                value={getByPath(values, path)}
                pending={pendingFiles[path] || []}
                onPending={(next) => onPendingFiles(path, next)}
                disabled={disabled}
                readOnly={readOnly}
                presentation={fieldPres}
              />
            </div>
          );
        }
        if (field.type === "array") {
          return (
            <div key={path} className={`col-md-${col} mb-2`}>
              <ArrayTableEditor
                field={field}
                value={getByPath(values, path)}
                onChange={(next) => onChange(path, next)}
                disabled={disabled}
                readOnly={readOnly}
                presentation={fieldPres}
              />
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
    if (field.type === "array") {
      const items = itemFields(field);
      const arr = Array.isArray(getByPath(values, path)) ? (getByPath(values, path) as Record<string, unknown>[]) : [];
      for (const row of arr) {
        const nested = validateLocal(items, row || {});
        if (nested) return nested;
      }
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

function collectFileFields(fields: DomainConfigField[]): DomainConfigField[] {
  const out: DomainConfigField[] = [];
  for (const field of fields) {
    if (field.type === "files") out.push(field);
    if (field.type === "object" && field.fields) {
      out.push(...collectFileFields(field.fields));
    }
  }
  return out;
}

function omitFileFields(
  values: Record<string, unknown>,
  fields: DomainConfigField[]
): Record<string, unknown> {
  const next = { ...values };
  for (const field of collectFileFields(fields)) {
    delete next[field.key];
  }
  return next;
}

function validatePendingFiles(
  fields: DomainConfigField[],
  values: Record<string, unknown>,
  pending: Record<string, File[]>
): string | null {
  for (const field of collectFileFields(fields)) {
    const selected = pending[field.key] || [];
    if (!selected.length) continue;
    const required = field.required_names || [];
    if (!required.length) continue;
    const status = artifactStatus(values[field.key]);
    const names = new Set([...(status.files || []), ...selected.map((file) => artifactFileName(file))]);
    if (required.some((name) => !names.has(name))) return field.label || field.key;
  }
  return null;
}

function collectSectionFields(section: DomainConfigSection): DomainConfigField[] {
  const fields = [...(section.fields || [])];
  for (const tab of section.tabs || []) {
    fields.push(...(tab.fields || []));
  }
  return fields;
}

function TabbedSectionCard({
  label,
  hint,
  tone,
  tabs,
  values,
  onChange,
  disabled,
  presentation,
  pendingFiles,
  onPendingFiles,
}: {
  label?: string;
  hint?: string;
  tone?: DomainConfigSection["tone"];
  tabs: NonNullable<DomainConfigSection["tabs"]>;
  values: Record<string, unknown>;
  onChange: (path: string, value: unknown) => void;
  disabled: boolean;
  presentation: Presentation;
  pendingFiles: Record<string, File[]>;
  onPendingFiles: (path: string, files: File[]) => void;
}) {
  const [active, setActive] = useState(0);
  const index = Math.min(Math.max(0, active), Math.max(0, tabs.length - 1));
  const tab = tabs[index];
  return (
    <div className={sectionCardClass(tone)}>
      <div className={sectionHeaderClass(tone, "pb-0")}>
        {label ? <h6 className="mb-2">{label}</h6> : null}
        <ul className="nav nav-tabs card-header-tabs" role="tablist">
          {tabs.map((item, i) => (
            <li className="nav-item" key={item.id || `tab-${i}`} role="presentation">
              <button
                type="button"
                className={`nav-link ${i === index ? "active" : ""}`}
                role="tab"
                aria-selected={i === index}
                onClick={() => setActive(i)}
              >
                {item.label || item.id || `Tab ${i + 1}`}
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div className="card-body">
        {hint ? (
          <div className={sectionHintClass(tone)} role="status">
            {hint}
          </div>
        ) : null}
        {tab?.hint ? (
          <div className={sectionHintClass(tone)} role="status">
            {tab.hint}
          </div>
        ) : null}
        <NestedFields
          fields={tab?.fields || []}
          values={values}
          onChange={onChange}
          disabled={disabled}
          presentation={presentation}
          pendingFiles={pendingFiles}
          onPendingFiles={onPendingFiles}
        />
      </div>
    </div>
  );
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
  const [pendingFiles, setPendingFiles] = useState<Record<string, File[]>>({});
  const [saving, setSaving] = useState(false);
  const [restartOpen, setRestartOpen] = useState(false);
  const [restarting, setRestarting] = useState(false);

  useEffect(() => {
    setValues(config || {});
  }, [machineName, config]);

  useEffect(() => {
    setPendingFiles({});
  }, [machineName]);

  const sections = schema.sections || [];
  const unsupported = Number(schema.version || 1) > SCHEMA_VERSION_SUPPORTED;
  const title = schema.title || t("machines.domainConfigTitle");
  const rootPresentation = schemaPresentation(schema);

  const allFields = useMemo(
    () => sections.flatMap((section) => collectSectionFields(section)),
    [sections]
  );

  const lastSchemaJson = useRef("");
  useEffect(() => {
    lastSchemaJson.current = "";
  }, [machineName]);
  useEffect(() => {
    if (!machineName) return undefined;
    let cancelled = false;
    const applyKeys = [
      "_apply_status",
      "_apply_message",
      "_restart_available",
      "_restart_eta_s",
      "_buffer_filled",
      "_buffer_need",
      "_sm_state",
      "_warnings",
      "_operation_state",
      "_active_engines",
      "_posterior",
      "_show_inputs_mapping",
      "_inputs_mapping_complete",
      "_missing_input_mappings",
      "_missing_field_attrs",
      "_missing_tags_message",
      "_inference_contract_aligned",
      "_inference_contract_mismatch",
      "_models_loaded",
    ];
    const refresh = async () => {
      try {
        const domain = await getMachineDomainConfig(machineName);
        if (cancelled || !domain?.config) return;
        const next = domain.config as Record<string, unknown>;
        setValues((prev) => {
          let changed = false;
          const merged = { ...prev };
          for (const key of applyKeys) {
            if (key in next) {
              if (merged[key] !== next[key]) {
                merged[key] = next[key];
                changed = true;
              }
            } else if (key in merged) {
              delete merged[key];
              changed = true;
            }
          }
          for (const key of Object.keys(next)) {
            if (!key.startsWith("artifacts_")) continue;
            if (JSON.stringify(merged[key]) !== JSON.stringify(next[key])) {
              merged[key] = next[key];
              changed = true;
            }
          }
          return changed ? merged : prev;
        });
        if (domain.schema) {
          try {
            const serialized = JSON.stringify(domain.schema);
            if (serialized !== lastSchemaJson.current) {
              lastSchemaJson.current = serialized;
              onSchemaUpdated?.(domain.schema);
            }
          } catch {
            onSchemaUpdated?.(domain.schema);
          }
        }
      } catch {
        /* keep the local form */
      }
    };
    void refresh();
    const timer = window.setInterval(() => {
      void refresh();
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
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
      return (domain?.config as Record<string, unknown> | undefined) || fallbackConfig;
    } catch {
      setValues(fallbackConfig);
      onConfigUpdated?.(fallbackConfig);
      return fallbackConfig;
    }
  };

  const handleSave = async () => {
    const invalid = validateLocal(allFields, values);
    if (invalid) {
      showToast(t("machines.domainConfigValidationError"), "error");
      return;
    }
    const incomplete = validatePendingFiles(allFields, values, pendingFiles);
    if (incomplete) {
      showToast(t("machines.domainConfigFilesIncomplete"), "error");
      return;
    }
    setSaving(true);
    try {
      let latest: Record<string, unknown> = { ...values };
      for (const field of collectFileFields(allFields)) {
        const selected = pendingFiles[field.key] || [];
        if (!selected.length) continue;
        const uploaded = await postMachineDomainFiles(machineName, field.key, selected);
        if (uploaded.config) {
          latest = { ...latest, ...uploaded.config };
          setValues(latest);
          onConfigUpdated?.(latest);
        }
      }
      const { _reset: _ignoredReset, _set_factory: _ignoredFactory, ...rawPayload } = latest;
      const payload = omitFileFields(rawPayload, allFields);
      const result = await putMachineDomainConfig(machineName, payload);
      const next = result.config || latest;
      setPendingFiles({});
      const saved = await applyServerState(next);
      if (isIncompleteSave(saved)) {
        const applyMessage = typeof saved._apply_message === "string" ? saved._apply_message.trim() : "";
        showToast(applyMessage || t("machines.domainConfigIncompleteWarning"), "warning");
      } else {
        showToast(t("machines.domainConfigSaved"), "success");
      }
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
      setPendingFiles({});
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
      const { _reset: _ignoredReset, _set_factory: _ignoredFactory, ...rawPayload } = values;
      const payload = omitFileFields(rawPayload, allFields);
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

  const handleRestart = async () => {
    setRestarting(true);
    try {
      const result = await putMachineDomainConfig(machineName, { _restart: true });
      const next = result.config || { ...values, _apply_status: "restarting" };
      setValues(next);
      onConfigUpdated?.(next);
      setRestartOpen(false);
      const eta = Number(next._restart_eta_s);
      beginProcessRestart(eta);
    } catch (err: any) {
      const data = err?.response?.data;
      const message =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        err?.message ??
        t("machines.domainConfigRestartError");
      showToast(message, "error");
    } finally {
      setRestarting(false);
    }
  };

  if (!sections.length) return null;

  const hasFactoryDefaults = Boolean(
    schema.ui_hints?.factory_defaults && Object.keys(schema.ui_hints.factory_defaults).length
  );
  const showSetFactory = schema.ui_hints?.show_set_factory !== false && hasFactoryDefaults;
  const factoryDefaults = (schema.ui_hints?.factory_defaults || {}) as Record<string, unknown>;
  const comparableKeys = visibleEditableKeys(allFields, values);
  const factoryKeys = comparableKeys.filter((key) => getByPath(factoryDefaults, key) !== undefined);
  const isDirtyVsSaved = valuesDiffer(values, config || {}, comparableKeys);
  const differsFromFactory = hasFactoryDefaults && valuesDiffer(values, factoryDefaults, factoryKeys);
  const hasPendingFiles = Object.values(pendingFiles).some((files) => files.length > 0);
  const canSave = isDirtyVsSaved || hasPendingFiles;
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
          <div>{values._apply_message}</div>
          {values._restart_available === true ? (
            <div className="mt-2">
              <Button
                type="button"
                variant="danger"
                loading={restarting}
                disabled={saving || restarting}
                onClick={() => setRestartOpen(true)}
              >
                {t("machines.domainConfigRestart")}
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
      {warningList(values._warnings)
        .filter((warning) => warning !== values._apply_message)
        .map((warning) => (
        <div key={warning} className="alert alert-warning py-2 small mb-3" role="status">
          {warning}
        </div>
      ))}
      <fieldset disabled={saving || restarting}>
        {sections.map((section, index) => {
          if (section.depends_on?.field) {
            if (!conditionMatches(section.depends_on, values)) {
              return null;
            }
          }
          const sectionPres = sectionPresentation(section, rootPresentation);
          const hasTabs = Boolean(section.tabs?.length);
          const hasFields = Boolean((section.fields || []).length);
          const key = section.id || `section-${index}`;
          const hint = section.hint ? (
            <div className={sectionHintClass(section.tone)} role="status">
              {section.hint}
            </div>
          ) : null;
          const fileHandlers = {
            pendingFiles,
            onPendingFiles: (path: string, files: File[]) =>
              setPendingFiles((prev) => ({ ...prev, [path]: files })),
          };
          if (hasTabs) {
            return (
              <TabbedSectionCard
                key={key}
                label={section.label}
                hint={section.hint}
                tone={section.tone}
                tabs={section.tabs || []}
                values={values}
                onChange={handleChange}
                disabled={saving || restarting}
                presentation={sectionPres}
                {...fileHandlers}
              />
            );
          }
          if (section.label && hasFields) {
            return (
              <div key={key} className={sectionCardClass(section.tone)}>
                <div className={sectionHeaderClass(section.tone)}>
                  <h6 className="mb-0">{section.label}</h6>
                </div>
                <div className="card-body">
                  {hint}
                  <NestedFields
                    fields={section.fields || []}
                    values={values}
                    onChange={handleChange}
                    disabled={saving || restarting}
                    presentation={sectionPres}
                    {...fileHandlers}
                  />
                </div>
              </div>
            );
          }
          return (
            <div key={key} className="mb-3">
              {section.label ? <h6 className="mb-3">{section.label}</h6> : null}
              {hint}
              {hasFields ? (
                <NestedFields
                  fields={section.fields || []}
                  values={values}
                  onChange={handleChange}
                  disabled={saving || restarting}
                  presentation={sectionPres}
                  {...fileHandlers}
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
            disabled={saving || restarting || !canRestoreFactory}
            onClick={handleReset}
          >
            {t("machines.domainConfigReset")}
          </Button>
          {showSetFactory ? (
            <Button
              type="button"
              variant="secondary"
              loading={saving}
              disabled={saving || restarting || !canSetFactory}
              onClick={handleSetFactory}
            >
              {t("machines.domainConfigSetFactory")}
            </Button>
          ) : null}
        </div>
        <Button
          type="button"
          variant="primary"
          loading={saving}
          disabled={saving || restarting || !canSave}
          onClick={handleSave}
        >
          {t("machines.domainConfigSave")}
          {hasPendingFiles ? ` (${t("machines.domainConfigFilesPendingSave")})` : ""}
        </Button>
      </div>
      <OpsConfirmModal
        open={restartOpen}
        title={t("machines.domainConfigRestartTitle")}
        body={t("machines.domainConfigRestartBody")}
        confirmLabel={t("machines.domainConfigRestart")}
        danger
        requireCheckbox
        checkboxLabel={t("machines.domainConfigRestartCheck")}
        busy={restarting}
        onCancel={() => {
          if (!restarting) setRestartOpen(false);
        }}
        onConfirm={handleRestart}
      />
    </Card>
  );
}
