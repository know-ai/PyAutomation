import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { AuthLayout } from "../layouts/AuthLayout";
import { Card } from "../components/Card";
import { Input } from "../components/Input";
import { Button } from "../components/Button";
import { login } from "../services/auth";
import { useAppDispatch } from "../hooks/useAppDispatch";
import { loginFailure, loginStart, loginSuccess } from "../store/slices/authSlice";
import { showToast } from "../utils/toast";
import { useTranslation } from "../hooks/useTranslation";

export function Login() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [remember, setRemember] = useState(false);

  // Verificar si hay un toast pendiente al cargar la página
  useEffect(() => {
    const showPendingToast = () => {
      try {
        const pendingToast = sessionStorage.getItem("pendingToast");
        if (pendingToast) {
          const toastData = JSON.parse(pendingToast);
          sessionStorage.removeItem("pendingToast");
          // Si tiene messageKey, traducirlo; si tiene message, usarlo directamente
          const message = toastData.messageKey ? t(toastData.messageKey) : toastData.message;
          const type = toastData.type || "warning";
          const duration = toastData.duration || 0;
          // Mostrar el toast después de asegurar que el DOM esté completamente listo
          showToast(message, type, duration);
        }
      } catch (_e) {
        // ignore errors
      }
    };

    // Usar requestAnimationFrame para asegurar que el DOM esté listo
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setTimeout(showPendingToast, 100);
      });
    });
  }, [t]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    dispatch(loginStart());
    try {
      const resp = await login({ username, password });
      const token = resp?.apiKey || resp?.token || resp?.api_key || null;
      const user = resp?.user || { username };
      if (!token) throw new Error(t("auth.tokenNotReceived"));
      dispatch(loginSuccess({ token, user }));
      navigate("/communications");
    } catch (err: any) {
      const status = err?.response?.status;
      const data = err?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error ??
        err?.message;

      let message: string;
      if (status === 401) {
        // Credenciales inválidas u otro error de autenticación
        message = backendMessage || t("auth.invalidCredentials");
      } else {
        // Cualquier otro error: mostrar mensaje del backend si existe
        message = backendMessage || t("auth.loginError");
      }

      setError(message);
      dispatch(loginFailure(message));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout>
      <div className="card card-outline card-primary">
        <div className="card-header text-center">
          <h1 className="m-0">
            <b>Py</b>Automation
          </h1>
          <p className="mb-0 text-muted">{t("auth.loginToContinue")}</p>
        </div>
        <div className="card-body login-card-body">
          <form onSubmit={handleSubmit} className="mb-3">
            <div className="input-group mb-3">
              <div className="form-floating flex-grow-1">
                <input
                  id="loginUsername"
                  type="text"
                  className="form-control"
                  placeholder={t("auth.username")}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
                <label htmlFor="loginUsername">{t("auth.username")}</label>
              </div>
              <div className="input-group-text">
                <span className="fas fa-user" aria-hidden="true" />
              </div>
            </div>

            <div className="input-group mb-3">
              <div className="form-floating flex-grow-1">
                <input
                  id="loginPassword"
                  type="password"
                  className="form-control"
                  placeholder={t("auth.password")}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <label htmlFor="loginPassword">{t("auth.password")}</label>
              </div>
              <div className="input-group-text">
                <span className="fas fa-lock" aria-hidden="true" />
              </div>
            </div>

            <div className="row align-items-center mb-3">
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

            {error && <div className="alert alert-danger py-2 mb-0">{error}</div>}
          </form>

          <div className="d-grid gap-2 mb-2">
            {/* <Link className="text-center d-block" to="/forgot-password">
              {t("auth.forgotPassword")}
            </Link> */}
            <Link className="text-center d-block" to="/signup">
              {t("auth.createNewAccount")}
            </Link>
          </div>
        </div>
      </div>
    </AuthLayout>
  );
}


