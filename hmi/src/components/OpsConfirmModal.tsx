import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Button } from "./Button";
import { useTranslation } from "../hooks/useTranslation";

type OpsConfirmModalProps = {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  requireCheckbox?: boolean;
  checkboxLabel?: string;
  requireTypedConfirm?: boolean;
  typedToken?: string;
  extra?: ReactNode;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void | Promise<void>;
};

export function OpsConfirmModal({
  open,
  title,
  body,
  confirmLabel,
  danger = false,
  requireCheckbox = false,
  checkboxLabel,
  requireTypedConfirm = false,
  typedToken = "CONFIRMAR",
  extra,
  busy = false,
  onCancel,
  onConfirm,
}: OpsConfirmModalProps) {
  const { t } = useTranslation();
  const [checked, setChecked] = useState(false);
  const [typed, setTyped] = useState("");

  useEffect(() => {
    if (!open) return;
    setChecked(false);
    setTyped("");
  }, [open]);

  if (!open) return null;

  const ready =
    (!requireCheckbox || checked) &&
    (!requireTypedConfirm || typed.trim().toUpperCase() === typedToken.toUpperCase());

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!ready || busy) return;
    await onConfirm();
  };

  return (
    <div
      className="modal fade show d-block perf-alarm-modal"
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      onClick={onCancel}
    >
      <div className="modal-dialog modal-dialog-centered" role="document" onClick={(event) => event.stopPropagation()}>
        <form className="modal-content" onSubmit={submit}>
          <div className="modal-header">
            <h5 className="modal-title">{title}</h5>
            <button type="button" className="btn-close" aria-label={t("common.close")} onClick={onCancel} />
          </div>
          <div className="modal-body">
            <div className={danger ? "perf-ops-warn" : undefined}>{body}</div>
            {extra}
            {requireCheckbox ? (
              <label className="perf-ops-check">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(event) => setChecked(event.target.checked)}
                />
                <span>{checkboxLabel}</span>
              </label>
            ) : null}
            {requireTypedConfirm ? (
              <label className="perf-ops-typed">
                <span>{t("performance.opsTypeConfirm", { token: typedToken })}</span>
                <input
                  type="text"
                  className="form-control"
                  value={typed}
                  autoComplete="off"
                  onChange={(event) => setTyped(event.target.value)}
                />
              </label>
            ) : null}
          </div>
          <div className="modal-footer">
            <Button type="button" variant="secondary" onClick={onCancel} disabled={busy}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" variant={danger ? "danger" : "primary"} disabled={!ready} loading={busy}>
              {confirmLabel || t("common.confirm")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
