import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { Button } from "./Button";
import { useAppSelector } from "../hooks/useAppSelector";
import { useTranslation } from "../hooks/useTranslation";
import { confirmOperatorAction, getOperatorConfirmation } from "../services/operatorConfirmation";
import { showToast } from "../utils/toast";

export type OperatorConfirmRequest = {
  method: "POST" | "PUT";
  path: string;
  to?: string;
  title: string;
  detail: string;
};

export type OperatorConfirmResult = {
  token: string | null;
};

type PendingConfirm = {
  request: OperatorConfirmRequest;
  resolve: (result: OperatorConfirmResult | null) => void;
};

type OperatorConfirmationContextValue = {
  confirm: (request: OperatorConfirmRequest) => Promise<OperatorConfirmResult | null>;
};

const OperatorConfirmationContext = createContext<OperatorConfirmationContextValue | null>(null);

export function useOperatorConfirmation(): OperatorConfirmationContextValue {
  const value = useContext(OperatorConfirmationContext);
  if (!value) {
    throw new Error("useOperatorConfirmation requires OperatorConfirmationProvider");
  }
  return value;
}

export function OperatorConfirmationProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const sessionUsername = useAppSelector((state) => state.auth.user?.username || "");
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const passwordRef = useRef<HTMLInputElement>(null);

  const readPolicy = useCallback(async () => {
    try {
      const policy = await getOperatorConfirmation();
      return policy.enabled;
    } catch {
      return false;
    }
  }, []);

  useEffect(() => {
    if (!pending) return;
    setUsername(sessionUsername);
    setPassword("");
    setError(null);
    const timer = window.setTimeout(() => passwordRef.current?.focus(), 0);
    return () => window.clearTimeout(timer);
  }, [pending, sessionUsername]);

  const confirm = useCallback(
    (request: OperatorConfirmRequest) => {
      return new Promise<OperatorConfirmResult | null>((resolve) => {
        void (async () => {
          const enabled = await readPolicy();
          if (!enabled) {
            resolve({ token: null });
            return;
          }
          setPending({ request, resolve });
        })();
      });
    },
    [readPolicy]
  );

  const close = (result: OperatorConfirmResult | null) => {
    pending?.resolve(result);
    setPending(null);
    setPassword("");
    setSubmitting(false);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!pending || submitting) return;
    if (!password) {
      setError(t("operatorConfirm.passwordRequired"));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const issued = await confirmOperatorAction({
        username: username.trim(),
        password,
        method: pending.request.method,
        path: pending.request.path,
        to: pending.request.to,
      });
      close({ token: issued.token });
    } catch (err: unknown) {
      const data = (err as { response?: { data?: { code?: string } } })?.response?.data;
      const message =
        data?.code === "AUTHZ_DENIED"
          ? t("operatorConfirm.notAuthorized")
          : t("operatorConfirm.invalidCredentials");
      setError(message);
      showToast(message, "error");
      setSubmitting(false);
    }
  };

  const dialog =
    pending &&
    createPortal(
      <div
        className="modal fade show d-block"
        style={{ backgroundColor: "rgba(0,0,0,0.55)", zIndex: 4000 }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="operator-confirm-title"
        onClick={() => {
          if (!submitting) close(null);
        }}
      >
        <div className="modal-dialog modal-dialog-centered" role="document" onClick={(event) => event.stopPropagation()}>
          <form className="modal-content" onSubmit={(event) => void handleSubmit(event)}>
            <div className="modal-header">
              <h5 className="modal-title" id="operator-confirm-title">
                {pending.request.title || t("operatorConfirm.title")}
              </h5>
              <button
                type="button"
                className="btn-close"
                aria-label={t("common.close")}
                disabled={submitting}
                onClick={() => close(null)}
              />
            </div>
            <div className="modal-body">
              <p className="mb-3">{pending.request.detail || t("operatorConfirm.lede")}</p>
              {error ? (
                <div className="alert alert-danger py-2" role="alert">
                  {error}
                </div>
              ) : null}
              <div className="mb-3">
                <label className="form-label" htmlFor="operator-confirm-username">
                  {t("operatorConfirm.username")}
                </label>
                <input
                  id="operator-confirm-username"
                  className="form-control"
                  name="operator-confirm-username"
                  autoComplete="off"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  disabled={submitting}
                  required
                />
              </div>
              <div>
                <label className="form-label" htmlFor="operator-confirm-password">
                  {t("operatorConfirm.password")}
                </label>
                <input
                  ref={passwordRef}
                  id="operator-confirm-password"
                  className="form-control"
                  name="operator-confirm-password"
                  type="password"
                  autoComplete="off"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  disabled={submitting}
                  required
                />
              </div>
            </div>
            <div className="modal-footer">
              <Button type="button" variant="secondary" disabled={submitting} onClick={() => close(null)}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" variant="primary" loading={submitting}>
                {t("operatorConfirm.submit")}
              </Button>
            </div>
          </form>
        </div>
      </div>,
      document.body
    );

  return (
    <OperatorConfirmationContext.Provider value={{ confirm }}>
      {children}
      {dialog}
    </OperatorConfirmationContext.Provider>
  );
}
