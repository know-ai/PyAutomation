export const SIDEBAR_MOBILE_MQ = "(max-width: 991.98px)";

export function isMobileViewport(): boolean {
  return window.matchMedia(SIDEBAR_MOBILE_MQ).matches;
}

export function isSidebarOpen(): boolean {
  const wrapper = document.querySelector(".app-wrapper");
  return (
    document.body.classList.contains("sidebar-open") ||
    Boolean(wrapper?.classList.contains("sidebar-open"))
  );
}

export function setSidebarOpen(open: boolean): void {
  const bodyCls = document.body.classList;
  const wrapperCls = document.querySelector(".app-wrapper")?.classList;

  if (open) {
    bodyCls.add("sidebar-open");
    bodyCls.remove("sidebar-collapse");
    wrapperCls?.add("sidebar-open");
    wrapperCls?.remove("sidebar-collapse");
  } else {
    bodyCls.remove("sidebar-open");
    bodyCls.add("sidebar-collapse");
    wrapperCls?.remove("sidebar-open");
    wrapperCls?.add("sidebar-collapse");
  }
}

export function toggleSidebar(): void {
  setSidebarOpen(!isSidebarOpen());
}

export function closeSidebarOnMobile(): void {
  if (isMobileViewport()) {
    setSidebarOpen(false);
  }
}
