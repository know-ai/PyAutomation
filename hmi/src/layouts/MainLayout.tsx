import { useEffect } from "react";
import type { PropsWithChildren } from "react";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { Footer } from "./Footer";
import { useTheme } from "../hooks/useTheme";

export function MainLayout({ children }: PropsWithChildren) {
  // Aplicar el tema
  useTheme();

  useEffect(() => {
    document.body.classList.add("layout-fixed", "sidebar-expand-lg", "sidebar-open", "bg-body-tertiary");
    return () => {
      document.body.classList.remove(
        "layout-fixed",
        "sidebar-expand-lg",
        "sidebar-open",
        "bg-body-tertiary"
      );
    };
  }, []);

  return (
    <div className="app-wrapper">
      {/* Header */}
      <Header />

      {/* Sidebar */}
      <Sidebar />

      {/* Content */}
      <main className="app-main">
        <div className="app-content pt-3">
          <div className="container-fluid">{children}</div>
        </div>
      </main>

      {/* Footer */}
      <Footer />
    </div>
  );
}


