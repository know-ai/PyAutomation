const HEADER = ["segment_name", "kp", "latitude", "longitude"] as const;
export const MAX_GEOSPATIAL_CSV_BYTES = 1_048_576;

export type GeospatialCsvIssue = {
  code:
    | "notCsv"
    | "tooLarge"
    | "empty"
    | "header"
    | "noRows"
    | "rowFields"
    | "segment"
    | "number"
    | "latitude"
    | "longitude"
    | "duplicate";
  row?: number;
};

export function inspectGeospatialCsv(fileName: string, size: number, text: string): GeospatialCsvIssue | null {
  if (!fileName.toLowerCase().endsWith(".csv")) {
    return { code: "notCsv" };
  }
  if (size > MAX_GEOSPATIAL_CSV_BYTES) {
    return { code: "tooLarge" };
  }
  const body = text.replace(/^\uFEFF/, "");
  if (!body.trim()) {
    return { code: "empty" };
  }

  const lines = body.split(/\r?\n/);
  const headerLine = lines.find((line) => line.trim().length > 0);
  if (!headerLine) {
    return { code: "empty" };
  }
  const header = splitCsvLine(headerLine);
  if (header.length !== HEADER.length || header.some((cell, index) => cell !== HEADER[index])) {
    return { code: "header" };
  }

  const seen = new Set<string>();
  let dataRows = 0;
  let started = false;
  for (const line of lines) {
    if (!started) {
      if (line.trim().length > 0) {
        started = true;
      }
      continue;
    }
    if (!line.trim()) {
      continue;
    }
    dataRows += 1;
    const row = dataRows + 1;
    const cells = splitCsvLine(line);
    if (cells.length !== HEADER.length) {
      return { code: "rowFields", row };
    }
    const [segmentName, kpRaw, latRaw, lonRaw] = cells;
    if (!segmentName) {
      return { code: "segment", row };
    }
    if (!kpRaw || !latRaw || !lonRaw) {
      return { code: "number", row };
    }
    const kp = Number(kpRaw);
    const latitude = Number(latRaw);
    const longitude = Number(lonRaw);
    if (!Number.isFinite(kp) || !Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      return { code: "number", row };
    }
    if (latitude < -90 || latitude > 90) {
      return { code: "latitude", row };
    }
    if (longitude < -180 || longitude > 180) {
      return { code: "longitude", row };
    }
    const key = `${segmentName}\0${kp}`;
    if (seen.has(key)) {
      return { code: "duplicate", row };
    }
    seen.add(key);
  }

  if (dataRows === 0) {
    return { code: "noRows" };
  }
  return null;
}

function splitCsvLine(line: string): string[] {
  const cells: string[] = [];
  let current = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (quoted) {
      if (char === '"') {
        if (line[index + 1] === '"') {
          current += '"';
          index += 1;
        } else {
          quoted = false;
        }
      } else {
        current += char;
      }
      continue;
    }
    if (char === '"') {
      quoted = true;
      continue;
    }
    if (char === ",") {
      cells.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }
  cells.push(current.trim());
  return cells;
}
