import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { AuthLayout } from "../layouts/AuthLayout";
import { Card } from "../components/Card";
import { Input } from "../components/Input";
import { Button } from "../components/Button";
import { signup } from "../services/auth";
import { useTranslation } from "../hooks/useTranslation";

export function Signup() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
    name: "",
    lastname: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onChange = (key: string, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await signup({
        username: form.username,
        email: form.email,
        password: form.password,
        name: form.name,
        lastname: form.lastname,
      });
      // Guardar toast de éxito en sessionStorage para que persista al navegar
      const toastData = {
        messageKey: "auth.signupSuccess",
        type: "success",
        duration: 5000, // 5 segundos
      };
      sessionStorage.setItem("pendingToast", JSON.stringify(toastData));
      navigate("/login");
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
      if (status === 400 && !backendMessage) {
        // Errores típicos de validación en signup (usuario ya existe, email inválido, etc.)
        message = t("auth.signupError");
      } else {
        message = backendMessage || t("auth.signupError");
      }

      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout>
      <Card title={t("auth.createAccount")}>
        <form onSubmit={handleSubmit}>
          <Input
            label={t("auth.username")}
            value={form.username}
            onChange={(e) => onChange("username", e.target.value)}
            required
          />
          <Input
            label={t("auth.email")}
            type="email"
            value={form.email}
            onChange={(e) => onChange("email", e.target.value)}
            required
          />
          <Input
            label={t("auth.password")}
            type="password"
            value={form.password}
            onChange={(e) => onChange("password", e.target.value)}
            required
          />
          <div className="row">
            <div className="col-6">
              <Input
                label={t("auth.name")}
                value={form.name}
                onChange={(e) => onChange("name", e.target.value)}
              />
            </div>
            <div className="col-6">
              <Input
                label={t("auth.lastname")}
                value={form.lastname}
                onChange={(e) => onChange("lastname", e.target.value)}
              />
            </div>
          </div>
          {error && <div className="alert alert-danger py-2">{error}</div>}
          <div className="d-flex justify-content-between align-items-center">
            <Button type="submit" loading={loading}>
              {t("auth.signup")}
            </Button>
            <Link to="/login">{t("auth.backToLogin")}</Link>
          </div>
        </form>
      </Card>
    </AuthLayout>
  );
}


