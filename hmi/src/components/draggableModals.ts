const INTERACTIVE = "button, input, textarea, select, a, label, .btn-close";
const EDGE = 48;

type Drag = {
  dialog: HTMLElement;
  pointerId: number;
  startX: number;
  startY: number;
  originX: number;
  originY: number;
};

export function clampDialogPosition(
  width: number,
  x: number,
  y: number,
  viewportWidth: number,
  viewportHeight: number
): { x: number; y: number } {
  const minX = Math.min(0, EDGE - width);
  const maxX = Math.max(minX, viewportWidth - EDGE);
  const maxY = Math.max(0, viewportHeight - EDGE);
  return {
    x: Math.min(maxX, Math.max(minX, x)),
    y: Math.min(maxY, Math.max(0, y)),
  };
}

function pinDialog(dialog: HTMLElement): DOMRect {
  const content = dialog.querySelector(".modal-content");
  const rect = (content instanceof HTMLElement ? content : dialog).getBoundingClientRect();
  dialog.style.position = "fixed";
  dialog.style.margin = "0";
  dialog.style.transform = "none";
  dialog.style.display = "block";
  dialog.style.minHeight = "0";
  dialog.style.height = "auto";
  dialog.style.width = `${rect.width}px`;
  dialog.style.maxWidth = "none";
  dialog.style.left = `${rect.left}px`;
  dialog.style.top = `${rect.top}px`;
  return rect;
}

function moveDialog(dialog: HTMLElement, x: number, y: number) {
  const next = clampDialogPosition(dialog.offsetWidth, x, y, window.innerWidth, window.innerHeight);
  dialog.style.left = `${next.x}px`;
  dialog.style.top = `${next.y}px`;
}

export function bindDraggableModals(root: Document | HTMLElement = document): () => void {
  let drag: Drag | null = null;

  const onPointerDown = (event: Event) => {
    if (!(event instanceof PointerEvent) || event.button !== 0) return;
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (target.closest(INTERACTIVE)) return;
    const header = target.closest(".modal-header");
    if (!(header instanceof HTMLElement)) return;
    const dialog = header.closest(".modal-dialog");
    if (!(dialog instanceof HTMLElement)) return;
    const rect = pinDialog(dialog);
    drag = {
      dialog,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: rect.left,
      originY: rect.top,
    };
    header.classList.add("modal-header--dragging");
    event.preventDefault();
  };

  const onPointerMove = (event: Event) => {
    if (!drag || !(event instanceof PointerEvent) || event.pointerId !== drag.pointerId) return;
    moveDialog(drag.dialog, drag.originX + event.clientX - drag.startX, drag.originY + event.clientY - drag.startY);
  };

  const onPointerUp = (event: Event) => {
    if (!drag || !(event instanceof PointerEvent) || event.pointerId !== drag.pointerId) return;
    drag.dialog.querySelector(".modal-header")?.classList.remove("modal-header--dragging");
    drag = null;
  };

  root.addEventListener("pointerdown", onPointerDown, true);
  root.addEventListener("pointermove", onPointerMove, true);
  root.addEventListener("pointerup", onPointerUp, true);
  root.addEventListener("pointercancel", onPointerUp, true);
  return () => {
    root.removeEventListener("pointerdown", onPointerDown, true);
    root.removeEventListener("pointermove", onPointerMove, true);
    root.removeEventListener("pointerup", onPointerUp, true);
    root.removeEventListener("pointercancel", onPointerUp, true);
    drag = null;
  };
}
