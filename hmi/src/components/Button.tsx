import type { ButtonHTMLAttributes, PropsWithChildren } from "react";
import clsx from "clsx";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  loading?: boolean;
  variant?: "primary" | "secondary" | "danger" | "success";
};

export function Button({
  children,
  className,
  loading = false,
  variant = "primary",
  ...props
}: PropsWithChildren<ButtonProps>) {
  return (
    <button
      className={clsx("btn", `btn-${variant}`, className)}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading ? "Cargando..." : children}
    </button>
  );
}


