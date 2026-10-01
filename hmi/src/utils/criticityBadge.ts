import type { CSSProperties } from "react";

export type CriticityBadgeStyle = {
  className: string;
  style?: CSSProperties;
};

/** Criticity 1–5. Other values have no badge color. */
export function criticityBadgeStyle(value: number): CriticityBadgeStyle | null {
  switch (value) {
    case 1:
      return { className: "badge bg-primary" };
    case 2:
      return { className: "badge bg-success" };
    case 3:
      return { className: "badge bg-warning text-dark" };
    case 4:
      return {
        className: "badge",
        style: { backgroundColor: "#ff9800", color: "#fff" },
      };
    case 5:
      return { className: "badge bg-danger" };
    default:
      return null;
  }
}
