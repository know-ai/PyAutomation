import { useState, type InputHTMLAttributes } from "react";
import clsx from "clsx";
import { useTranslation } from "../hooks/useTranslation";

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  error?: string;
  hint?: string;
  hintTone?: "success" | "danger" | "muted";
};

export function Input({
  label,
  error,
  hint,
  hintTone = "muted",
  className,
  type,
  ...props
}: InputProps) {
  const { t } = useTranslation();
  const [showPassword, setShowPassword] = useState(false);
  const isPassword = type === "password";
  const resolvedType = isPassword && showPassword ? "text" : type;
  const hintClass =
    hintTone === "success" ? "text-success" : hintTone === "danger" ? "text-danger" : "text-muted";

  const control = (
    <input
      type={resolvedType}
      className={clsx("form-control", className, { "is-invalid": !!error })}
      {...props}
    />
  );

  return (
    <div className="form-group mb-3">
      {label && <label className="form-label">{label}</label>}
      {isPassword ? (
        <div className="input-group">
          {control}
          <button
            type="button"
            className="input-group-text login-password-toggle"
            onClick={() => setShowPassword((visible) => !visible)}
            aria-label={showPassword ? t("auth.hidePassword") : t("auth.showPassword")}
            aria-pressed={showPassword}
            title={showPassword ? t("auth.hidePassword") : t("auth.showPassword")}
          >
            <i className={showPassword ? "bi bi-eye-slash" : "bi bi-eye"} aria-hidden="true" />
          </button>
        </div>
      ) : (
        control
      )}
      {error && <div className="invalid-feedback d-block">{error}</div>}
      {hint && !error ? <div className={clsx("form-text", hintClass)}>{hint}</div> : null}
    </div>
  );
}
