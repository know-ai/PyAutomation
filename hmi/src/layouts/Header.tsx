import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "../hooks/useTranslation";
import { toggleSidebar } from "./sidebarDom";
import { DatabaseStatus } from "../components/DatabaseStatus";
import { HeaderClock } from "../components/HeaderClock";

export function Header() {
  const { t } = useTranslation();
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

  const toggleSidebarMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    toggleSidebar();
  }, []);

  const toggleFullscreen = useCallback(async (e: React.MouseEvent) => {
    e.preventDefault();
    try {
      if (!document.fullscreenElement) {
        await document.documentElement.requestFullscreen();
        setIsFullscreen(true);
      } else {
        await document.exitFullscreen();
        setIsFullscreen(false);
      }
    } catch {
      // ignore fullscreen errors
    }
  }, []);

  useEffect(() => {
    const onChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  return (
    <nav className="app-header navbar navbar-expand bg-body">
      <div className="container-fluid app-header__bar">
        <ul className="navbar-nav">
          <li className="nav-item">
            <a
              className="nav-link"
              href="#"
              role="button"
              onClick={toggleSidebarMenu}
              aria-label={t("header.menu")}
            >
              <i className="bi bi-list" />
            </a>
          </li>
        </ul>

        <HeaderClock />

        <ul className="navbar-nav app-header__actions">
          <li className="nav-item d-flex align-items-center">
            <DatabaseStatus compact />
          </li>
          <li className="nav-item">
            <a
              className="nav-link"
              href="#"
              role="button"
              onClick={toggleFullscreen}
              title={isFullscreen ? t("header.exitFullscreen") : t("header.fullscreen")}
              aria-label={isFullscreen ? t("header.exitFullscreen") : t("header.fullscreen")}
            >
              {isFullscreen ? (
                <i className="bi bi-fullscreen-exit" />
              ) : (
                <i className="bi bi-arrows-fullscreen" />
              )}
            </a>
          </li>
        </ul>
      </div>
    </nav>
  );
}
