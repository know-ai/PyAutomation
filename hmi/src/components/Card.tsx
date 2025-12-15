import type { PropsWithChildren, ReactNode } from "react";
import clsx from "clsx";

type CardProps = PropsWithChildren<{
  title?: ReactNode;
  footer?: ReactNode;
  className?: string;
  style?: React.CSSProperties;
  headerClassName?: string;
  bodyClassName?: string;
}>;

export function Card({ title, footer, className, style, headerClassName, bodyClassName, children }: CardProps) {
  return (
    <div className={clsx("card shadow-sm", className)} style={style}>
      {title && (
        <div className={clsx("card-header py-1", headerClassName)}>
          {typeof title === "string" ? (
            <h3 className="card-title m-0">{title}</h3>
          ) : (
            title
          )}
        </div>
      )}
      <div
        className={clsx("card-body", bodyClassName)}
        style={
          style?.display === "flex"
            ? { flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }
            : undefined
        }
      >
        {children}
      </div>
      {footer && <div className="card-footer">{footer}</div>}
    </div>
  );
}
