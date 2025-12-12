import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { AuthLayout } from "../layouts/AuthLayout";
import { Card } from "../components/Card";
import { Input } from "../components/Input";
import { Button } from "../components/Button";
import { login } from "../services/auth";
import { useAppDispatch } from "../hooks/useAppDispatch";
import { loginFailure, loginStart, loginSuccess } from "../store/slices/authSlice";

export function Login() {
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [remember, setRemember] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    dispatch(loginStart());
    try {
      const resp = await login({ username, password });
      const token = resp?.apiKey || resp?.token || resp?.api_key || null;
      const user = resp?.user || { username };
      if (!token) throw new Error("Token no recibido");
      dispatch(loginSuccess({ token, user }));
      navigate("/communications");
    } catch (err: any) {
      const message = err?.response?.data?.message || err?.message || "Error al iniciar sesión";
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
          <p className="mb-0 text-muted">Inicia sesión para continuar</p>
        </div>
        <div className="card-body login-card-body">
          <form onSubmit={handleSubmit} className="mb-3">
            <div className="input-group mb-3">
              <div className="form-floating flex-grow-1">
                <input
                  id="loginUsername"
                  type="text"
                  className="form-control"
                  placeholder="Usuario"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
                <label htmlFor="loginUsername">Usuario</label>
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
                  placeholder="Contraseña"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
                <label htmlFor="loginPassword">Contraseña</label>
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
                    Recordarme
                  </label>
                </div>
              </div>
              <div className="col-5 text-end">
                <Button type="submit" loading={loading} className="w-100">
                  Entrar
                </Button>
              </div>
            </div>

            {error && <div className="alert alert-danger py-2 mb-0">{error}</div>}
          </form>

          <div className="d-grid gap-2 mb-2">
            <Link className="text-center d-block" to="/forgot-password">
              ¿Olvidó su contraseña?
            </Link>
            <Link className="text-center d-block" to="/signup">
              Crear una nueva cuenta
            </Link>
          </div>
        </div>
      </div>
    </AuthLayout>
  );
}


