import { useEffect } from "react";
import type { PropsWithChildren } from "react";

export function AuthLayout({ children }: PropsWithChildren) {
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

