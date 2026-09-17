/** Client-side mirror of automation.tag_naming.qualify_user_tag_name (HMI create form). */

export type TagNameValidation = {
  ok: boolean;
  message?: string;
  qualifiedName?: string;
  baseName?: string;
};

export function tagNameBaseSegment(name: string): string {
  const parts = (name || "").trim().split(".").filter(Boolean);
  return parts.length ? parts[parts.length - 1] : (name || "").trim();
}

/** Prefix shown in the create-tag name input: ``Manufacturer.Segment.`` */
export function edgeTagNamePrefix(site: string, area: string): string {
  if (!site || !area) return "";
  return `${site}.${area}.`;
}

/**
 * Keep the Edge Device prefix in the name input while the user completes the base.
 * If they type a bare name, it is appended after the prefix.
 */
export function applyCreateTagNamePrefix(
  rawName: string,
  site: string,
  area: string,
  previousName = ""
): string {
  const prefix = edgeTagNamePrefix(site, area);
  if (!prefix) return rawName;
  if (rawName.startsWith(prefix)) return rawName;
  if (!rawName.trim()) return prefix;
  const deletingIntoPrefix =
    previousName.startsWith(prefix) &&
    rawName.length === previousName.length - 1 &&
    prefix.startsWith(rawName);
  if (deletingIntoPrefix) return prefix;
  const parts = rawName.split(".").filter(Boolean);
  if (parts.length <= 1) return `${prefix}${parts[0] || ""}`;
  return rawName;
}

function isIncompleteEdgePrefix(raw: string, site: string, area: string): boolean {
  if (!site || !area) return false;
  const parts = raw.split(".").filter(Boolean);
  return parts.length === 2 && parts[0] === site && parts[1] === area;
}

export function validateUserTagNameInput(
  name: string,
  site: string,
  area: string
): TagNameValidation {
  const raw = (name || "").trim();
  if (!raw) {
    return { ok: false, message: "required" };
  }
  if (!site || !area) {
    return { ok: true, qualifiedName: raw, baseName: tagNameBaseSegment(raw) };
  }

  const prefix = `${site}.${area}`;
  const parts = raw.split(".").filter(Boolean);

  if (isIncompleteEdgePrefix(raw, site, area)) {
    return { ok: false, message: "incomplete" };
  }

  if (parts.length === 1) {
    const base = parts[0];
    return {
      ok: true,
      qualifiedName: `${prefix}.${base}`,
      baseName: base,
    };
  }
  if (parts.length === 2) {
    return {
      ok: false,
      message: "twoParts",
      qualifiedName: `${prefix}.${parts[1]}`,
    };
  }
  if (parts.length === 3) {
    const [inputSite, inputArea, base] = parts;
    if (inputSite !== site || inputArea !== area) {
      return {
        ok: false,
        message: "mismatch",
        qualifiedName: `${prefix}.${base}`,
      };
    }
    return { ok: true, qualifiedName: raw, baseName: base };
  }
  return { ok: false, message: "reserved" };
}
