import { useEffect, useRef } from "react";

type SparklineProps = {
  values: number[];
  tone?: "ok" | "warn" | "error" | "unknown" | "shelved";
  className?: string;
};

const STROKE: Record<NonNullable<SparklineProps["tone"]>, string> = {
  ok: "#198754",
  warn: "#c9a227",
  error: "#dc3545",
  unknown: "#6c757d",
  shelved: "#6c757d",
};

export function Sparkline({ values, tone = "unknown", className }: SparklineProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || 120;
    const height = canvas.clientHeight || 36;
    canvas.width = Math.max(1, Math.floor(width * dpr));
    canvas.height = Math.max(1, Math.floor(height * dpr));
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);
    if (values.length < 2) return;

    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const step = values.length === 1 ? 0 : (width - 2) / (values.length - 1);

    ctx.beginPath();
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = STROKE[tone];
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    values.forEach((value, index) => {
      const x = 1 + index * step;
      const y = height - 2 - ((value - min) / span) * (height - 4);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }, [tone, values]);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      aria-hidden="true"
      style={{ width: "100%", height: "2.25rem", display: "block" }}
    />
  );
}
