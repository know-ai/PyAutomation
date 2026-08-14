import { useEffect } from "react";
import type { PropsWithChildren } from "react";
import { useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { Footer } from "./Footer";
import { useTheme } from "../hooks/useTheme";
import { useDisplayTimezone } from "../hooks/useDisplayTimezone";
import { useSocket } from "../hooks/useSocket";
import { useTranslation } from "../hooks/useTranslation";
import { useMemoryWatchdog } from "../hooks/useMemoryWatchdog";
import { socketService } from "../services/socket";
import { DatabaseStatusProvider } from "../hooks/useDatabaseStatus";
import { DatabaseUnavailableOverlay } from "../components/DatabaseUnavailableOverlay";
import {
  SIDEBAR_MOBILE_MQ,
  closeSidebarOnMobile,
  setSidebarOpen,
} from "./sidebarDom";

export function MainLayout({ children }: PropsWithChildren) {
  useTheme();
  useDisplayTimezone();
  useSocket();
  useMemoryWatchdog(512);

  useEffect(() => {
    if (!import.meta.env.DEV) {
      return;
    }
    const expose = () => socketService.listenerCount();
    (window as unknown as { __pyaSocketListeners?: typeof expose }).__pyaSocketListeners = expose;
    return () => {
      delete (window as unknown as { __pyaSocketListeners?: typeof expose }).__pyaSocketListeners;
    };
  }, []);
  const location = useLocation();
  const { t } = useTranslation();

  useEffect(() => {
    document.body.classList.add("layout-fixed", "sidebar-expand-lg", "bg-body-tertiary");
    const mq = window.matchMedia(SIDEBAR_MOBILE_MQ);
    const applyViewportSidebar = () => {
      setSidebarOpen(!mq.matches);
    };
    applyViewportSidebar();
    mq.addEventListener("change", applyViewportSidebar);
    return () => {
      mq.removeEventListener("change", applyViewportSidebar);
      document.body.classList.remove(
        "layout-fixed",
        "sidebar-expand-lg",
        "sidebar-open",
        "sidebar-collapse",
        "bg-body-tertiary"
      );
    };
  }, []);

  useEffect(() => {
    closeSidebarOnMobile();
  }, [location.pathname]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        closeSidebarOnMobile();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <DatabaseStatusProvider>
    <div className="app-wrapper">
      <Header />
      <Sidebar />
      <main className="app-main">
        <div className="app-main-stage">
          <DatabaseUnavailableOverlay />
          <div className="app-content pt-3">
            <div className="container-fluid">{children}</div>
          </div>
        </div>
      </main>
      <Footer />
      <div
        className="sidebar-overlay"
        role="button"
        tabIndex={-1}
        aria-label={t("common.close")}
        onClick={() => closeSidebarOnMobile()}
      />
    </div>
    </DatabaseStatusProvider>
  );
}


