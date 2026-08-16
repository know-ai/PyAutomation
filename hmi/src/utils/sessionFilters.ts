const TAG_FILTER_KEYS = ["trends_selectedTags", "datalogger_selectedTags"] as const;

export function readSessionTags(key: (typeof TAG_FILTER_KEYS)[number]): string[] {
  try {
    localStorage.removeItem(key);
  } catch {
    // ignore
  }
  try {
    const saved = sessionStorage.getItem(key);
    if (!saved) return [];
    const parsed = JSON.parse(saved);
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}

export function writeSessionTags(key: (typeof TAG_FILTER_KEYS)[number], tags: string[]): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(tags));
  } catch {
    // ignore
  }
}

export function clearSessionTagFilters(): void {
  for (const key of TAG_FILTER_KEYS) {
    try {
      sessionStorage.removeItem(key);
      localStorage.removeItem(key);
    } catch {
      // ignore
    }
  }
}
