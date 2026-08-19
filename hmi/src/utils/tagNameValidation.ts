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
