import { useMemo, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { AuthLayout } from "../layouts/AuthLayout";
import { Card } from "../components/Card";
import { Input } from "../components/Input";
import { Button } from "../components/Button";
import { DatabaseConfigForm } from "../components/DatabaseConfigForm";
import { signup } from "../services/auth";
import { useTranslation } from "../hooks/useTranslation";
import { showToast } from "../utils/toast";

export function Signup() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
    confirmPassword: "",
    name: "",
    lastname: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showDatabaseConfig, setShowDatabaseConfig] = useState(false);
  const [databaseEventId, setDatabaseEventId] = useState<string | null>(null);

  const onChange = (key: string, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const passwordsMatch =
    form.password.length > 0 && form.password === form.confirmPassword;
  const canCreate = Boolean(form.username.trim()) && passwordsMatch && !loading;

  const confirmHint = useMemo(() => {
    if (!form.password && !form.confirmPassword) return undefined;
    if (!form.confirmPassword) {
      return { text: t("auth.repeatPasswordHint"), tone: "muted" as const };
    }
    if (passwordsMatch) {
      return { text: t("auth.passwordsMatch"), tone: "success" as const };
    }
    return { text: t("auth.passwordsMismatch"), tone: "danger" as const };
  }, [form.password, form.confirmPassword, passwordsMatch, t]);

  const attemptSignup = async () => {
    if (!form.username.trim() || !passwordsMatch) return;
    setError(null);
    setLoading(true);
    try {
      await signup({
        username: form.username.trim(),
        email: form.email.trim(),
        password: form.password,
        name: form.name,
        lastname: form.lastname,
      });

      const toastData = {
        message: t("auth.signupSuccess"),
        type: "success",
        duration: 5000,
      };
      sessionStorage.setItem("pendingToast", JSON.stringify(toastData));

      setLoading(false);

      setTimeout(() => {
        navigate("/login", { replace: true });
      }, 0);
    } catch (err: any) {
      const status = err?.response?.status;
      const data = err?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error ??
        err?.message;

      const isDatabaseError =
        data?.error_type === "database_connection_error" ||
        (status === 503 &&
          backendMessage &&
          (backendMessage.includes("CONNECTING DATABASE ERROR") ||
            backendMessage.includes("Database is not configured") ||
            backendMessage.includes("Cannot connect to the database") ||
            backendMessage.includes("Database connection") ||
            backendMessage.includes("connection to server") ||
            backendMessage.includes("cannot be persisted")));

      if (isDatabaseError) {
        const eventId =
          typeof data?.event_id === "string" && data.event_id.trim() ? data.event_id.trim() : null;
        setDatabaseEventId(eventId);
        setShowDatabaseConfig(true);
        setError(backendMessage);
        if (eventId) {
          showToast(t("auth.databaseUnavailableWithEventId", { eventId }), "warning", 0);
        }
      } else {
        let message: string;
        if (status === 400 && !backendMessage) {
          message = t("auth.signupError");
        } else {
          message = backendMessage || t("auth.signupError");
        }
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await attemptSignup();
  };

  const handleDatabaseConnectionSuccess = () => {
    setShowDatabaseConfig(false);
    setDatabaseEventId(null);
    setError(null);
    setTimeout(() => {
      attemptSignup();
    }, 500);
  };

  return (
    <AuthLayout>
      {showDatabaseConfig ? (
        <DatabaseConfigForm
          onConnectionSuccess={handleDatabaseConnectionSuccess}
          onCancel={() => {
            setShowDatabaseConfig(false);
            setDatabaseEventId(null);
          }}
          eventId={databaseEventId}
        />
      ) : (
      <Card title={t("auth.createAccount")}>
        <form onSubmit={handleSubmit}>
          <Input
            label={t("auth.username")}
            value={form.username}
            onChange={(e) => onChange("username", e.target.value)}
            autoComplete="username"
            required
          />
          <Input
            label={t("auth.emailOptional")}
            type="email"
            value={form.email}
            onChange={(e) => onChange("email", e.target.value)}
            autoComplete="email"
          />
          <Input
            label={t("auth.password")}
            type="password"
            value={form.password}
            onChange={(e) => onChange("password", e.target.value)}
            autoComplete="new-password"
            required
          />
          <Input
            label={t("auth.repeatPassword")}
            type="password"
            value={form.confirmPassword}
            onChange={(e) => onChange("confirmPassword", e.target.value)}
            autoComplete="new-password"
            required
            hint={confirmHint?.text}
            hintTone={confirmHint?.tone}
          />
          <div className="row">
            <div className="col-6">
              <Input
                label={t("auth.name")}
                value={form.name}
                onChange={(e) => onChange("name", e.target.value)}
                autoComplete="given-name"
              />
            </div>
            <div className="col-6">
              <Input
                label={t("auth.lastname")}
                value={form.lastname}
                onChange={(e) => onChange("lastname", e.target.value)}
                autoComplete="family-name"
              />
            </div>
          </div>
          {error && <div className="alert alert-danger py-2">{error}</div>}
          <div className="d-flex justify-content-between align-items-center">
            <Button type="submit" loading={loading} disabled={!canCreate}>
              {t("auth.signup")}
            </Button>
            <Link to="/login">{t("auth.backToLogin")}</Link>
          </div>
        </form>
      </Card>
      )}
    </AuthLayout>
  );
}
