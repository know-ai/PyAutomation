/** Minimal card shape so this module does not import React components. */
export type SanitizableCard = {
  id: string;
  title: string;
  tagNames: string[];
  timeSpanMinutes: number;
  x: number;
  y: number;
  w: number;
  h: number;
  showThresholds?: boolean;
};

/**
 * Drop obsolete card fields (I-4) and optionally drop tag names that
 * are no longer in the station catalog (I-3). Empty catalog = no filter.
 */
export function sanitizeCard<T extends SanitizableCard>(
  card: T,
  catalog?: Set<string>
): Omit<T, "showThresholds"> {
  const { showThresholds: _ignored, ...rest } = card;
  const names = Array.isArray(rest.tagNames) ? rest.tagNames : [];
  const tagNames =
    catalog && catalog.size > 0 ? names.filter((name) => catalog.has(name)) : names;
  return { ...rest, tagNames };
}

export function filterChartsToCatalog<T extends SanitizableCard>(
  charts: T[],
  catalog: Set<string>
): T[] {
  if (!catalog.size) return charts;
  let changed = false;
  const next = charts.map((chart) => {
    const sanitized = sanitizeCard(chart, catalog) as T;
    if (
      sanitized.tagNames.length !== chart.tagNames.length ||
      sanitized.tagNames.some((name, index) => name !== chart.tagNames[index]) ||
      "showThresholds" in chart
    ) {
      changed = true;
    }
    return sanitized;
  });
  return changed ? next : charts;
}
