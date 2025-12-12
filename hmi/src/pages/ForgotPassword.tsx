import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "../layouts/AuthLayout";
import { Card } from "../components/Card";
import { Input } from "../components/Input";
import { Button } from "../components/Button";
import { forgotPassword } from "../services/auth";
import { useTranslation } from "../hooks/useTranslation";

export function ForgotPassword() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setLoading(true);
    try {
      const resp = await forgotPassword(username, newPassword);
      setSuccess(resp?.message || t("auth.resetPassword"));
      setTimeout(() => navigate("/login"), 1500);
    } catch (err: any) {
      const message =
        err?.response?.data?.message || err?.message || t("auth.resetPassword");
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout>
      <Card title={t("auth.resetPassword")}>
        <form onSubmit={handleSubmit}>
          <Input
            label={t("auth.username")}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
          <Input
            label={t("auth.newPassword")}
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
          {error && <div className="alert alert-danger py-2">{error}</div>}
          {success && <div className="alert alert-success py-2">{success}</div>}
          <div className="d-flex justify-content-between align-items-center">
            <Button type="submit" loading={loading}>
              {t("auth.resetPassword")}
            </Button>
            <Link to="/login">{t("auth.backToLogin")}</Link>
          </div>
        </form>
      </Card>
    </AuthLayout>
  );
}


