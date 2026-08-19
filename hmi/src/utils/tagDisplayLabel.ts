import type { Tag } from "../services/tags";
import { tagNameBaseSegment } from "./tagNameValidation";

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
 * Label for chart legends and compact tag chips.
 * Uses DB display_name when it is a friendly label; never repeats Site.Area prefixes.
 */
export function resolveTagDisplayLabel(tag: Tag | undefined, qualifiedName: string): string {
  const name = (tag?.name ?? qualifiedName).trim();
  if (!name) return qualifiedName;

  const displayName = (tag?.display_name ?? "").trim();
  if (displayName && looksLikeFriendlyLabel(displayName) && displayName !== name) {
    return displayName;
  }

  if (looksLikeQualifiedTagName(name)) {
    return tagNameBaseSegment(name);
  }

  return name;
}
