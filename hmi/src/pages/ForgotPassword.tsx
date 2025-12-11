import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AuthLayout } from "../layouts/AuthLayout";
import { Card } from "../components/Card";
import { Input } from "../components/Input";
import { Button } from "../components/Button";
import { forgotPassword } from "../services/auth";

export function ForgotPassword() {
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
      setSuccess(resp?.message || "Contraseña restablecida");
      setTimeout(() => navigate("/login"), 1500);
    } catch (err: any) {
      const message =
        err?.response?.data?.message || err?.message || "Error al restablecer contraseña";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout>
      <Card title="Restablecer contraseña">
        <form onSubmit={handleSubmit}>
          <Input
            label="Usuario"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
          <Input
            label="Nueva contraseña"
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
          {error && <div className="alert alert-danger py-2">{error}</div>}
          {success && <div className="alert alert-success py-2">{success}</div>}
          <div className="d-flex justify-content-between align-items-center">
            <Button type="submit" loading={loading}>
              Restablecer
            </Button>
            <a href="/login">Volver a login</a>
          </div>
        </form>
      </Card>
    </AuthLayout>
  );
}


