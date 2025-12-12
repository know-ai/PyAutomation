import { useEffect } from "react";
import type { PropsWithChildren } from "react";
import { useTheme } from "../hooks/useTheme";

export function AuthLayout({ children }: PropsWithChildren) {
  // Aplicar el tema
  useTheme();

  useEffect(() => {
    document.body.classList.add("login-page", "bg-body-secondary");
    return () => {
      document.body.classList.remove("login-page", "bg-body-secondary");
    };
  }, []);

  return (
    <div className="login-page" style={{ minHeight: "100vh" }}>
      <div className="login-box">{children}</div>
    </div>
  );
}

