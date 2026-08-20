import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { AuthLayout } from "../layouts/AuthLayout";
import { Button } from "../components/Button";
import { DatabaseConfigForm } from "../components/DatabaseConfigForm";
import { login } from "../services/auth";
import { useAppDispatch } from "../hooks/useAppDispatch";
import { useAppSelector } from "../hooks/useAppSelector";
import { loginFailure, loginStart, loginSuccess } from "../store/slices/authSlice";
import { showToast } from "../utils/toast";
import { useTranslation } from "../hooks/useTranslation";
import { isSystemUser, SYSTEM_HOME_PATH } from "../utils/systemUser";

const DATABASE_ERROR_HINTS = [
  "connecting database error",
  "database is not configured",
  "cannot connect to the database",
  "database connection",
  "connection to server",
  "database_connection_error",
];

type LoginErrorKey =
  | "auth.invalidCredentials"
  | "auth.loginError"
  | "auth.networkError"
  | "auth.databaseUnavailable"
  | "auth.tooManyAttempts"
  | "auth.tokenNotReceived";

function extractBackendText(err: unknown): string {
  const data = (err as { response?: { data?: unknown } })?.response?.data;
  if (typeof data === "string") return data;
  if (data && typeof data === "object") {
    const payload = data as { message?: unknown; detail?: unknown; error?: unknown; error_type?: unknown };
    const parts = [payload.message, payload.detail, payload.error, payload.error_type];
    return parts.filter((part): part is string => typeof part === "string").join(" ");
  }
  const message = (err as { message?: unknown })?.message;
  return typeof message === "string" ? message : "";
}

function resolveLoginError(err: unknown): { kind: "database" | "credentials"; key: LoginErrorKey } {
  const axiosErr = err as {
    response?: { status?: number; data?: { error_type?: string } };
    code?: string;
  };
  const status = axiosErr?.response?.status;
  const errorType = axiosErr?.response?.data?.error_type;
  const backendText = extractBackendText(err).toLowerCase();

  const isDatabaseError =
    status === 503 ||
    errorType === "database_connection_error" ||
    DATABASE_ERROR_HINTS.some((hint) => backendText.includes(hint));

  if (isDatabaseError) {
    return { kind: "database", key: "auth.databaseUnavailable" };
  }

  if (!axiosErr?.response || axiosErr.code === "ECONNABORTED" || axiosErr.code === "ERR_NETWORK") {
    return { kind: "credentials", key: "auth.networkError" };
  }

  if (status === 429) {
    return { kind: "credentials", key: "auth.tooManyAttempts" };
  }

  if (status === 401 || status === 403 || errorType === "authentication_error") {
    return { kind: "credentials", key: "auth.invalidCredentials" };
  }

  return { kind: "credentials", key: "auth.loginError" };
}

export function Login() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const existingToken = useAppSelector((s) => s.auth.token);
  const authStatus = useAppSelector((s) => s.auth.status);
  const existingUser = useAppSelector((s) => s.auth.user);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errorKey, setErrorKey] = useState<LoginErrorKey | null>(null);
  const [loading, setLoading] = useState(false);
  const [remember, setRemember] = useState(false);
  const [showDatabaseConfig, setShowDatabaseConfig] = useState(false);

  const credentialsInvalid = errorKey === "auth.invalidCredentials";

  useEffect(() => {
    if (authStatus === "authenticated" && existingToken) {
      navigate(isSystemUser(existingUser) ? SYSTEM_HOME_PATH : "/communications", {
        replace: true,
      });
    }
  }, [authStatus, existingToken, existingUser, navigate]);

  useEffect(() => {
    const showPendingToast = () => {
      try {
        const pendingToast = sessionStorage.getItem("pendingToast");
        if (pendingToast) {
          const toastData = JSON.parse(pendingToast);
          sessionStorage.removeItem("pendingToast");
          const message = toastData.messageKey ? t(toastData.messageKey) : toastData.message;
          const type = toastData.type || "warning";
          const duration = toastData.duration || 0;
          showToast(message, type, duration);
        }
      } catch (_e) {
        // ignore errors
      }
    };

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setTimeout(showPendingToast, 100);
      });
    });
  }, [t]);

  const clearError = () => {
    if (errorKey) {
      setErrorKey(null);
    }
  };

  const attemptLogin = async () => {
    setErrorKey(null);
    setLoading(true);
    dispatch(loginStart());
    try {
      const resp = await login({ username, password });
      const token = resp?.apiKey || resp?.token || resp?.api_key || null;
      const user = resp?.user || {
        username: resp?.username || username,
        role: resp?.role,
      };
      if (!token) {
        setErrorKey("auth.tokenNotReceived");
        dispatch(loginFailure("auth.tokenNotReceived"));
        return;
      }
      dispatch(loginSuccess({ token, user }));
      navigate(isSystemUser(user) ? SYSTEM_HOME_PATH : "/communications");
    } catch (err: unknown) {
      const resolved = resolveLoginError(err);
      if (resolved.kind === "database") {
        setShowDatabaseConfig(true);
        setErrorKey(null);
        dispatch(loginFailure(resolved.key));
      } else {
        setErrorKey(resolved.key);
        dispatch(loginFailure(resolved.key));
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) {
      return;
    }
    await attemptLogin();
  };

  const handleDatabaseConnectionSuccess = () => {
    setShowDatabaseConfig(false);
    setErrorKey(null);
    setTimeout(() => {
      attemptLogin();
    }, 500);
  };

  return (
    <AuthLayout>
      {showDatabaseConfig ? (
        <DatabaseConfigForm
          onConnectionSuccess={handleDatabaseConnectionSuccess}
          onCancel={() => setShowDatabaseConfig(false)}
        />
      ) : (
      <div className="card card-outline card-primary">
        <div className="card-header text-center">
          <h1 className="m-0">
            <b>Py</b>Automation
          </h1>
          <p className="mb-0 text-muted">{t("auth.loginToContinue")}</p>
        </div>
        <div className="card-body login-card-body">
          <form onSubmit={handleSubmit} className="mb-3" noValidate>
            {errorKey && (
              <div className="login-feedback" role="alert" aria-live="polite" id="loginError">
                <i className="bi bi-exclamation-circle login-feedback__icon" aria-hidden="true" />
                <p className="login-feedback__text">{t(errorKey)}</p>
              </div>
            )}

            <div className="input-group mb-3">
              <div className="form-floating flex-grow-1">
                <input
                  id="loginUsername"
                  type="text"
                  className={`form-control${credentialsInvalid ? " is-invalid" : ""}`}
                  placeholder={t("auth.username")}
                  value={username}
                  onChange={(e) => {
                    setUsername(e.target.value);
                    clearError();
                  }}
                  autoComplete="username"
                  spellCheck={false}
                  aria-invalid={credentialsInvalid}
                  aria-describedby={errorKey ? "loginError" : undefined}
                  required
                />
                <label htmlFor="loginUsername">{t("auth.username")}</label>
              </div>
              <div className="input-group-text">
                <span className="bi bi-person" aria-hidden="true" />
              </div>
            </div>

            <div className="input-group mb-3">
              <div className="form-floating flex-grow-1">
                <input
                  id="loginPassword"
                  type={showPassword ? "text" : "password"}
                  className={`form-control${credentialsInvalid ? " is-invalid" : ""}`}
                  placeholder={t("auth.password")}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    clearError();
                  }}
                  autoComplete="current-password"
                  aria-invalid={credentialsInvalid}
                  aria-describedby={errorKey ? "loginError" : undefined}
                  required
                />
                <label htmlFor="loginPassword">{t("auth.password")}</label>
              </div>
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

            <div className="row align-items-center mb-0">
              <div className="col-7">
                <div className="form-check">
                  <input
                    id="rememberMe"
                    type="checkbox"
                    className="form-check-input"
                    checked={remember}
                    onChange={(e) => setRemember(e.target.checked)}
                  />
                  <label className="form-check-label" htmlFor="rememberMe">
                    {t("auth.rememberMe")}
                  </label>
                </div>
              </div>
              <div className="col-5 text-end">
                <Button type="submit" loading={loading} className="w-100">
                  {t("auth.login")}
                </Button>
              </div>
            </div>
          </form>

          <div className="d-grid gap-2 mb-2">
            <Link className="text-center d-block" to="/signup">
              {t("auth.createNewAccount")}
            </Link>
          </div>
        </div>
      </div>
      )}
    </AuthLayout>
  );
}
