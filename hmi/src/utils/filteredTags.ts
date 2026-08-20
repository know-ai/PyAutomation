/** Wavelet-derived filtered tag helpers (mirror of backend naming). */

const FILTER_SUFFIX = ".f";

export function isFilteredDerivativeName(name?: string | null): boolean {
  return Boolean(name) && String(name).endsWith(FILTER_SUFFIX);
}

export function sourceTagName(filteredName: string): string {
  const name = String(filteredName || "").trim();
  if (name.endsWith(FILTER_SUFFIX)) {
    return name.slice(0, -FILTER_SUFFIX.length);
  }
  return name;
}
