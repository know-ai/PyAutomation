import type { Tag } from "../services/tags";
import { isFilteredDerivativeName, sourceTagName } from "./filteredTags";

/** True when the value looks like Site.Area.Base (dotted identifier path). */
function looksLikeQualifiedTagName(value: string): boolean {
  return /^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)+$/.test(value.trim());
}

/** True when display_name is meant for humans, not a qualified tag path. */
function looksLikeFriendlyLabel(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) return false;
  if (/\s/.test(trimmed)) return true;
  return !looksLikeQualifiedTagName(trimmed);
}

/**
 * Some runtime catalogs prefix Area again before Site.Area.Base
 * (e.g. Linea2.Supe.Linea2.FI_01). Strip the leading area when the remainder
 * is still a qualified path.
 */
export function stripErroneousAreaPrefix(name: string, area?: string | null): string {
  const trimmed = (name || "").trim();
  if (!trimmed || !area) return trimmed;
  const prefix = `${area}.`;
  if (!trimmed.startsWith(prefix)) return trimmed;
  const rest = trimmed.slice(prefix.length);
  const parts = rest.split(".").filter(Boolean);
  return parts.length >= 2 ? rest : trimmed;
}

export function stripFilterDisplaySuffix(value: string): string {
  const trimmed = (value || "").trim();
  if (trimmed.endsWith(".filtro") && trimmed.length > ".filtro".length) {
    return trimmed.slice(0, -".filtro".length);
  }
  if (trimmed.endsWith(".f") && trimmed.length > ".f".length) {
    return trimmed.slice(0, -".f".length);
  }
  return trimmed;
}

function withFilterSuffix(base: string, filtered: boolean): string {
  const raw = stripFilterDisplaySuffix(base);
  return filtered ? `${raw}.f` : raw;
}

/** Friendly segment for historian filters and table headers. */
export function historianFriendlyTagLabel(qualifiedName: string): string {
  const filtered = isFilteredDerivativeName(qualifiedName);
  const source = filtered ? sourceTagName(qualifiedName) : qualifiedName;
  const normalized = stripErroneousAreaPrefix(source);
  const parts = normalized.split(".").filter(Boolean);
  if (!parts.length) return withFilterSuffix(qualifiedName, filtered);

  const sysIndex = parts.findIndex((part) => part === "SYS" || part.startsWith("SYS."));
  if (sysIndex >= 0) {
    return withFilterSuffix(parts.slice(sysIndex).join("."), filtered);
  }
  if (parts.length === 3) {
    return withFilterSuffix(parts[2], filtered);
  }
  if (parts.length > 3) {
    return withFilterSuffix(parts.slice(-3).join("."), filtered);
  }
  return withFilterSuffix(parts[parts.length - 1], filtered);
}

/** Strip multi-edge display prefix ``Area · Friendly``. */
function stripScopedFriendlyPrefix(value: string): string {
  const sep = " · ";
  const idx = value.indexOf(sep);
  if (idx > 0) {
    return value.slice(idx + sep.length).trim();
  }
  return value;
}

/**
 * Label for chart legends and compact tag chips.
 * Uses DB display_name when it is a friendly label; never repeats Site.Area prefixes.
 * Filtered (.f) tags always render as ``{DisplayNameRaw}.f``.
 */
export function resolveTagDisplayLabel(tag: Tag | undefined, qualifiedName: string): string {
  const name = stripErroneousAreaPrefix(tag?.name ?? qualifiedName, tag?.area);
  if (!name) return qualifiedName;
  const filtered = isFilteredDerivativeName(name);
  const sourceName = filtered ? sourceTagName(name) : name;

  const displayName = stripFilterDisplaySuffix(
    stripScopedFriendlyPrefix((tag?.display_name ?? "").trim())
  );
  if (displayName && looksLikeFriendlyLabel(displayName) && displayName !== sourceName && displayName !== name) {
    return withFilterSuffix(displayName, filtered);
  }

  if (looksLikeQualifiedTagName(sourceName) || looksLikeQualifiedTagName(name)) {
    return historianFriendlyTagLabel(filtered ? `${sourceName}.f` : sourceName);
  }

  return withFilterSuffix(sourceName || name, filtered);
}

/** MultiSelect option label for historian catalog tags (DataLogger / Trends). */
export function buildHistorianTagOptionLabel(
  tag: Pick<Tag, "name" | "display_name" | "area">
): string {
  const friendly = resolveTagDisplayLabel(tag as Tag, tag.name);
  return tag.area ? `${friendly} (${tag.area})` : friendly;
}
