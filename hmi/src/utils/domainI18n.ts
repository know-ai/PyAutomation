/** Translate DomainConfigurable schema/banners. Missing keys fall back to the API string. */

export type TranslateFn = (key: string, params?: Record<string, string | number>) => string;

export type DomainI18nPart = {
  key?: string;
  params?: Record<string, string | number>;
  itemKeys?: string[];
};

export type DomainI18nPayload = DomainI18nPart & {
  parts?: DomainI18nPart[];
};

export function tx(
  t: TranslateFn,
  fallback?: string | null,
  key?: string | null,
  params?: Record<string, string | number>
): string {
  if (key) {
    const translated = t(key, params);
    if (translated !== key) return translated;
  }
  const raw = (fallback || "").trim();
  if (raw.startsWith("domain.") || raw.startsWith("machines.")) {
    const translated = t(raw, params);
    if (translated !== raw) return translated;
  }
  return fallback || key || "";
}

export function renderI18nPart(t: TranslateFn, part: DomainI18nPart | undefined): string {
  if (!part?.key) return "";
  const params: Record<string, string | number> = { ...(part.params || {}) };
  for (const [name, value] of Object.entries(params)) {
    if (typeof value === "string" && (value.startsWith("domain.") || value.startsWith("machines."))) {
      params[name] = tx(t, value, value);
    }
  }
  if (part.itemKeys?.length) {
    params.items = part.itemKeys.map((itemKey) => tx(t, itemKey, itemKey)).join(", ");
  }
  return tx(t, "", part.key, params);
}

export function renderI18nPayload(t: TranslateFn, payload: unknown): string {
  if (!payload || typeof payload !== "object") return "";
  const data = payload as DomainI18nPayload;
  if (Array.isArray(data.parts) && data.parts.length) {
    return data.parts.map((part) => renderI18nPart(t, part)).filter(Boolean).join(" ");
  }
  return renderI18nPart(t, data);
}

export function inferDomainNs(schema: { i18n_ns?: string; title?: string } | null | undefined): string {
  const explicit = String(schema?.i18n_ns || "").trim();
  if (explicit) return explicit;
  const title = String(schema?.title || "").toUpperCase();
  if (title.includes("OBSERVER")) return "domain.observer";
  if (title.includes("PFM")) return "domain.pfm";
  if (title.includes("NPW")) return "domain.npw";
  if (title.includes("PPA")) return "domain.ppa";
  if (title.includes("LDS")) return "domain.lds";
  return "";
}

export function domainEngineLabel(t: TranslateFn, ns: string): string {
  const key = ns ? `${ns}.engine` : "";
  return tx(t, ns.replace(/^domain\./, "").toUpperCase(), key);
}

const TAB_STATUS_SUFFIXES: Array<[string, string]> = [
  [" · incompleto", "domain.common.tabIncomplete"],
  [" · cargando", "domain.common.tabLoading"],
  [" · pendiente de carga", "domain.common.tabPendingLoad"],
];

export function translateTabLabel(t: TranslateFn, raw: string | undefined, key?: string, ns?: string, id?: string): string {
  const label = raw || "";
  for (const [suffix, statusKey] of TAB_STATUS_SUFFIXES) {
    if (label.endsWith(suffix)) {
      const base = label.slice(0, -suffix.length);
      return `${base} · ${t(statusKey)}`;
    }
  }
  return tx(t, label, key || (ns && id ? `${ns}.tabs.${id}` : undefined));
}

export function fillingCount(
  filled: unknown,
  need: unknown
): { f: number; n: number } | null {
  const n = Number(need);
  const f = Number(filled);
  if (!Number.isFinite(n) || n <= 0 || !Number.isFinite(f)) return null;
  return { f: Math.max(0, Math.trunc(f)), n: Math.trunc(n) };
}

export function translateApplyBanner(
  t: TranslateFn,
  values: Record<string, unknown>,
  ns: string
): string {
  const engine = domainEngineLabel(t, ns);
  const raw = String(values._apply_message || "");
  const fromPayload = renderI18nPayload(t, values._apply_message_i18n);
  if (fromPayload) return fromPayload;
  const status = String(values._apply_status || "");
  const count = fillingCount(values._buffer_filled, values._buffer_need);
  if (status === "filling") {
    return t("domain.banners.filling", {
      engine,
      filled: count?.f ?? "—",
      need: count?.n ?? "—",
    });
  }
  if (status === "rearm") {
    return t("domain.banners.rearm", { engine, need: count?.n ?? "—" });
  }
  if (status === "restarting") {
    return t("domain.banners.restarting");
  }
  if (status === "pending_restart") {
    return t("domain.banners.pendingDiskModels", { engine });
  }
  if (status === "pending") {
    if (/motores/i.test(raw)) return t("domain.banners.pendingMotors");
    return t("domain.banners.pendingLeak", { engine });
  }
  if (status === "blocked") {
    const mapped = renderI18nPayload(t, values._subscribe_mapping_i18n);
    if (mapped && !raw) return mapped;
    const fromBlocked = renderI18nPayload(t, values._apply_message_i18n);
    if (fromBlocked) return fromBlocked;
    if (/fluido/i.test(raw) && /densidades/i.test(raw)) return t("domain.lds.banners.needsFluid");
    if (/motor de detección está activo|ningún motor/i.test(raw)) {
      return t("domain.lds.banners.noEngines");
    }
    if (/mapeo de entradas|asignar canales/i.test(raw)) return t("domain.banners.inputsMapping");
    if (/volumétr/i.test(raw)) return t("domain.banners.volumetricDensity", { engine });
    if (/lds indica/i.test(raw)) return t("domain.banners.fluidMismatch", { engine });
    if (/permanece en waiting/i.test(raw)) return t("domain.banners.waitingTags", { engine });
    if (/modelo/i.test(raw)) return t("domain.banners.needsModels", { engine });
  }
  return raw;
}

export function translateWarning(
  t: TranslateFn,
  warning: string,
  i18n: unknown,
  ns: string
): string {
  const fromPayload = renderI18nPayload(t, i18n);
  if (fromPayload) return fromPayload;
  if (/ningún motor/i.test(warning)) return t("domain.lds.banners.noEngines");
  if (/fluido/i.test(warning) && /densidades/i.test(warning)) return t("domain.lds.banners.needsFluid");
  if (/mapeo de entradas|asignar canales/i.test(warning)) return t("domain.banners.inputsMapping");
  if (/volumétr/i.test(warning)) return t("domain.banners.volumetricDensity", { engine: domainEngineLabel(t, ns) });
  if (/lds indica/i.test(warning)) return t("domain.banners.fluidMismatch", { engine: domainEngineLabel(t, ns) });
  if (/permanece en waiting/i.test(warning)) return t("domain.banners.waitingTags", { engine: domainEngineLabel(t, ns) });
  if (/presión de entrada/i.test(warning) && /falta/i.test(warning)) {
    return t("domain.subscribe.pressure.inletOnly", { engine: domainEngineLabel(t, ns) });
  }
  if (/presión de salida/i.test(warning) && /falta/i.test(warning)) {
    return t("domain.subscribe.pressure.outletOnly", { engine: domainEngineLabel(t, ns) });
  }
  return warning;
}

export function translateSubscribeHint(t: TranslateFn, raw: string, i18n: unknown): string {
  const fromPayload = renderI18nPayload(t, i18n);
  if (fromPayload) return fromPayload;
  return raw;
}

export function translateMachineState(t: TranslateFn, state: string): string {
  return tx(t, state, `machines.states.${String(state || "").toLowerCase()}`);
}

export function translateMachineClassification(t: TranslateFn, value: string): string {
  const slug = String(value || "")
    .toLowerCase()
    .trim()
    .replace(/\s+/g, "_");
  return tx(t, value, slug ? `machines.classifications.${slug}` : undefined);
}

type AnyRecord = Record<string, unknown>;

function asRecord(value: unknown): AnyRecord | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as AnyRecord) : null;
}

const RING_OPTION_I18N: Record<string, string> = {
  inlet_mass_flow: "domain.attrs.inletFlow",
  outlet_mass_flow: "domain.attrs.outletFlow",
  inlet_pressure: "domain.attrs.inletPressure",
  outlet_pressure: "domain.attrs.outletPressure",
};

function translateOption(t: TranslateFn, option: unknown, ns: string, fieldKey: string): unknown {
  if (typeof option === "string") {
    return tx(t, option, ns ? `${ns}.fields.${fieldKey}_opt_${option}` : undefined);
  }
  const rec = asRecord(option);
  if (!rec) return option;
  const value = String(rec.value ?? "");
  const key = String(rec.label_key || "") || (ns && value ? `${ns}.fields.${fieldKey}_opt_${value}` : "");
  const durationKey = /^\d+$/.test(value) ? `domain.common.duration.${value}` : "";
  const ringKey = RING_OPTION_I18N[value] || "";
  let label = tx(t, String(rec.label || value), key || durationKey || ringKey || undefined);
  if (ringKey && String(rec.label || "").includes(" → ")) {
    const right = String(rec.label).split(" → ").slice(1).join(" → ");
    const left = tx(t, String(rec.label).split(" → ")[0] || value, ringKey);
    label = right ? `${left} → ${right}` : left;
  } else if (value === "" && String(rec.label || "").includes(" → ")) {
    const right = String(rec.label).split(" → ").slice(1).join(" → ");
    label = `${t("domain.common.unmapped")} → ${right}`;
  }
  return {
    ...rec,
    label,
  };
}

function translateField(t: TranslateFn, field: unknown, ns: string, parentKey?: string): unknown {
  const rec = asRecord(field);
  if (!rec) return field;
  const key = String(rec.key || "");
  const path = parentKey ? `${parentKey}_${key}` : key;
  const base = ns && path ? `${ns}.fields.${path}` : "";
  const commonBase = path ? `domain.common.fields.${path}` : "";
  const next: AnyRecord = { ...rec };
  const role = String(rec.artifact_role || "");
  const engine = String(rec.artifact_engine || "").toLowerCase();
  const roleKey = role && engine ? `domain.${engine}.roles.${role}` : "";
  next.label = tx(
    t,
    String(rec.label || ""),
    String(rec.label_key || "") || roleKey || base || undefined
  );
  if (next.label === rec.label && commonBase) {
    next.label = tx(t, String(rec.label || ""), commonBase);
  }
  if (rec.help != null || rec.help_key) {
    next.help = tx(t, String(rec.help || ""), String(rec.help_key || "") || (base ? `${base}Help` : undefined));
    if (next.help === rec.help && commonBase) {
      next.help = tx(t, String(rec.help || ""), `${commonBase}Help`);
    }
  }
  if (rec.short_label) {
    next.short_label = tx(t, String(rec.short_label), String(rec.short_label_key || "") || (base ? `${base}Short` : undefined));
  }
  if (rec.true_label) {
    next.true_label = tx(t, String(rec.true_label), String(rec.true_label_key || "") || "common.yes");
  }
  if (rec.false_label) {
    next.false_label = tx(t, String(rec.false_label), String(rec.false_label_key || "") || "common.no");
  }
  if (Array.isArray(rec.options)) {
    next.options = rec.options.map((option) => translateOption(t, option, ns, path));
  }
  if (Array.isArray(rec.fields)) {
    next.fields = rec.fields.map((child) => translateField(t, child, ns, path));
  }
  const items = asRecord(rec.items);
  if (items) {
    const properties = asRecord(items.properties);
    const nextItems: AnyRecord = { ...items };
    if (properties) {
      const translated: AnyRecord = {};
      for (const [propKey, prop] of Object.entries(properties)) {
        translated[propKey] = translateField(t, { ...(asRecord(prop) || {}), key: propKey }, ns, path);
      }
      nextItems.properties = translated;
    }
    if (Array.isArray(items.fields)) {
      nextItems.fields = items.fields.map((child) => translateField(t, child, ns, path));
    }
    next.items = nextItems;
  }
  return next;
}

function translateTab(t: TranslateFn, tab: unknown, ns: string): unknown {
  const rec = asRecord(tab);
  if (!rec) return tab;
  return {
    ...rec,
    label: translateTabLabel(t, String(rec.label || ""), String(rec.label_key || ""), ns, String(rec.id || "")),
    hint: rec.hint
      ? tx(t, String(rec.hint), String(rec.hint_key || "") || (ns && rec.id ? `${ns}.tabs.${rec.id}Hint` : undefined))
      : rec.hint,
    fields: Array.isArray(rec.fields) ? rec.fields.map((field) => translateField(t, field, ns)) : rec.fields,
  };
}

function translateSection(t: TranslateFn, section: unknown, ns: string): unknown {
  const rec = asRecord(section);
  if (!rec) return section;
  const id = String(rec.id || "");
  return {
    ...rec,
    label: tx(t, String(rec.label || ""), String(rec.label_key || "") || (ns && id ? `${ns}.sections.${id}` : undefined)),
    hint: rec.hint
      ? tx(t, String(rec.hint), String(rec.hint_key || "") || (ns && id ? `${ns}.sections.${id}Hint` : undefined))
      : rec.hint,
    fields: Array.isArray(rec.fields) ? rec.fields.map((field) => translateField(t, field, ns)) : rec.fields,
    tabs: Array.isArray(rec.tabs) ? rec.tabs.map((tab) => translateTab(t, tab, ns)) : rec.tabs,
  };
}

export function translateDomainSchema<T extends { title?: string; i18n_ns?: string; sections?: unknown[]; ui_hints?: AnyRecord }>(
  schema: T,
  t: TranslateFn
): T {
  const ns = inferDomainNs(schema);
  const hints = asRecord(schema.ui_hints) || {};
  const subscribe = asRecord(hints.subscribe_hints);
  const nextHints: AnyRecord = { ...hints };
  if (subscribe) {
    const translated: AnyRecord = {};
    for (const [attr, text] of Object.entries(subscribe)) {
      translated[attr] = tx(
        t,
        String(text || ""),
        ns ? `${ns}.subscribeHints.${attr}` : undefined
      );
    }
    nextHints.subscribe_hints = translated;
  }
  return {
    ...schema,
    title: tx(t, schema.title || "", String((schema as AnyRecord).title_key || "") || (ns ? `${ns}.title` : undefined)),
    sections: Array.isArray(schema.sections)
      ? (schema.sections.map((section) => translateSection(t, section, ns)) as T["sections"])
      : schema.sections,
    ui_hints: nextHints as T["ui_hints"],
  };
}

