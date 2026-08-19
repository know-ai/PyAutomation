import type { Tag } from "../services/tags";

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

/** Friendly segment for historian filters and table headers. */
export function historianFriendlyTagLabel(qualifiedName: string): string {
  const normalized = stripErroneousAreaPrefix(qualifiedName);
  const parts = normalized.split(".").filter(Boolean);
  if (!parts.length) return qualifiedName;

  const sysIndex = parts.findIndex((part) => part === "SYS" || part.startsWith("SYS."));
  if (sysIndex >= 0) {
    return parts.slice(sysIndex).join(".");
  }
  if (parts.length === 3) {
    return parts[2];
  }
  if (parts.length > 3) {
    return parts.slice(-3).join(".");
  }
  return parts[parts.length - 1];
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
 */
export function resolveTagDisplayLabel(tag: Tag | undefined, qualifiedName: string): string {
  const name = stripErroneousAreaPrefix(tag?.name ?? qualifiedName, tag?.area);
  if (!name) return qualifiedName;

  const displayName = stripScopedFriendlyPrefix((tag?.display_name ?? "").trim());
  if (displayName && looksLikeFriendlyLabel(displayName) && displayName !== name) {
    return displayName;
  }

  if (looksLikeQualifiedTagName(name)) {
    return historianFriendlyTagLabel(name);
  }

  return name;
}

/** MultiSelect option label for historian catalog tags (DataLogger / Trends). */
export function buildHistorianTagOptionLabel(
  tag: Pick<Tag, "name" | "display_name" | "area">
): string {
  const friendly = resolveTagDisplayLabel(tag as Tag, tag.name);
  return tag.area ? `${friendly} (${tag.area})` : friendly;
}
