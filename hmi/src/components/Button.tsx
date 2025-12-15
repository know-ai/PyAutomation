import type { ButtonHTMLAttributes, PropsWithChildren } from "react";
import clsx from "clsx";
import { useTranslation } from "../hooks/useTranslation";

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
  const { t } = useTranslation();

  return (
    <button
      className={clsx("btn", `btn-${variant}`, className)}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading ? t("common.loading") : children}
    </button>
  );
}


