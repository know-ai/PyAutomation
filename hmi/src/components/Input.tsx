import type { InputHTMLAttributes } from "react";
import clsx from "clsx";

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label?: string;
  error?: string;
};

export function Input({ label, error, className, ...props }: InputProps) {
  return (
    <div className="form-group mb-3">
      {label && <label className="form-label">{label}</label>}
      <input className={clsx("form-control", className, { "is-invalid": !!error })} {...props} />
      {error && <div className="invalid-feedback d-block">{error}</div>}
    </div>
  );
}


