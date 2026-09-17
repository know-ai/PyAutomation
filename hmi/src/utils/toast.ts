/**
 * Utilidad para mostrar toasts usando Bootstrap 5 CSS (sin JS)
 */

export type ToastType = "success" | "error" | "warning" | "info";

export const showToast = (
  message: string,
  type: ToastType = "info",
  duration: number = 5000,
  action?: { label: string; onClick: () => void }
) => {
  let toastContainer = document.getElementById("toast-container");
  if (!toastContainer) {
    toastContainer = document.createElement("div");
    toastContainer.id = "toast-container";
    toastContainer.style.cssText = `
      position: fixed;
      top: 0;
      right: 0;
      padding: 1rem;
      z-index: 99999;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      max-width: 400px;
      pointer-events: none;
    `;
    document.body.appendChild(toastContainer);
  }

  const toastId = `toast-${Date.now()}`;
  const toast = document.createElement("div");
  toast.id = toastId;
  toast.setAttribute("role", "alert");
  toast.setAttribute("aria-live", "assertive");
  toast.setAttribute("aria-atomic", "true");

  const bgColor = getBootstrapColor(type);
  const textColor = type === "warning" ? "#000" : "#fff";
  const buttonColor = type === "warning" ? "#000" : "#fff";

  toast.style.cssText = `
    display: flex;
    align-items: center;
    color: ${textColor};
    background-color: ${bgColor};
    border: 0;
    border-radius: 0.375rem;
    padding: 0.75rem;
    box-shadow: 0 0.125rem 0.25rem rgba(0, 0, 0, 0.075), 0 0.5rem 1rem rgba(0, 0, 0, 0.15);
    pointer-events: auto;
    animation: slideInRight 0.3s ease-out;
    min-width: 300px;
  `;

  const toastBody = document.createElement("div");
  toastBody.style.cssText = "display: flex; align-items: center; width: 100%;";

  const toastContent = document.createElement("div");
  toastContent.style.cssText = `flex: 1; padding-right: 0.5rem; color: ${textColor};`;
  toastContent.textContent = message;

  const closeToast = () => {
    toast.style.animation = "slideOutRight 0.3s ease-in";
    setTimeout(() => {
      toast.remove();
      if (toastContainer && toastContainer.children.length === 0) {
        toastContainer.remove();
      }
    }, 300);
  };

  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.setAttribute("aria-label", "Close");
  closeButton.style.cssText = `
    background: transparent;
    border: none;
    color: ${buttonColor};
    font-size: 1.5rem;
    font-weight: 700;
    line-height: 1;
    opacity: 0.75;
    cursor: pointer;
    padding: 0;
    width: 1.5rem;
    height: 1.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: opacity 0.2s;
  `;
  closeButton.innerHTML = "&times;";
  closeButton.onmouseover = () => {
    closeButton.style.opacity = "1";
  };
  closeButton.onmouseout = () => {
    closeButton.style.opacity = "0.75";
  };
  closeButton.onclick = closeToast;

  toastBody.appendChild(toastContent);
  if (action) {
    const actionButton = document.createElement("button");
    actionButton.type = "button";
    actionButton.textContent = action.label;
    actionButton.style.cssText = `
      margin-right: 0.5rem;
      background: transparent;
      border: 1px solid ${buttonColor};
      color: ${buttonColor};
      border-radius: 0.25rem;
      padding: 0.15rem 0.5rem;
      font-size: 0.8rem;
      cursor: pointer;
      white-space: nowrap;
    `;
    actionButton.onclick = () => {
      action.onClick();
      closeToast();
    };
    toastBody.appendChild(actionButton);
  }
  toastBody.appendChild(closeButton);
  toast.appendChild(toastBody);
  toastContainer.appendChild(toast);

  if (duration > 0) {
    setTimeout(closeToast, duration);
  }

  if (!document.getElementById("toast-animations")) {
    const style = document.createElement("style");
    style.id = "toast-animations";
    style.textContent = `
      @keyframes slideInRight {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
      }
      @keyframes slideOutRight {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
      }
    `;
    document.head.appendChild(style);
  }
};

const getBootstrapColor = (type: ToastType): string => {
  switch (type) {
    case "success":
      return "#198754";
    case "error":
      return "#dc3545";
    case "warning":
      return "#ffc107";
    case "info":
    default:
      return "#0dcaf0";
  }
};
