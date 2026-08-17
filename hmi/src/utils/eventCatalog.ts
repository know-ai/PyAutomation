type TranslateFn = (key: string, params?: Record<string, string | number>) => string;

const lookup = (t: TranslateFn, section: "message" | "classification", raw: string): string | null => {
  const key = `events.catalog.${section}.${raw}`;
  const translated = t(key);
  return translated === key ? null : translated;
};

/** OPC UA audit stores ``"{canonical}: {client}"``. */
const MESSAGE_PREFIXES = [
  "OPC UA client connection failed",
  "OPC UA client reconnect failed",
  "OPC UA client disconnected",
  "OPC UA client reconnecting",
  "OPC UA client reconnected",
  "OPC UA client connected",
].sort((a, b) => b.length - a.length);

export function translateEventClassification(
  value: string | null | undefined,
  t: TranslateFn
): string {
  if (value == null || value === "") return "-";
  return lookup(t, "classification", value) || value;
}

export function translateEventMessage(value: string | null | undefined, t: TranslateFn): string {
  if (value == null || value === "") return "-";
  const exact = lookup(t, "message", value);
  if (exact) return exact;

  for (const prefix of MESSAGE_PREFIXES) {
    if (value === prefix) {
      return lookup(t, "message", prefix) || value;
    }
    const withColon = `${prefix}: `;
    if (value.startsWith(withColon)) {
      const head = lookup(t, "message", prefix) || prefix;
      return `${head}: ${value.slice(withColon.length)}`;
    }
  }
  return value;
}
