import type { PropsWithChildren, ReactNode } from "react";
import clsx from "clsx";

type CardProps = PropsWithChildren<{
  title?: ReactNode;
  footer?: ReactNode;
  className?: string;
}>;

export function Card({ title, footer, className, children }: CardProps) {
  return (
    <div className={clsx("card shadow-sm", className)}>
      {title && (
        <div className="card-header">
          {typeof title === "string" ? (
            <h3 className="card-title m-0">{title}</h3>
          ) : (
            title
          )}
        </div>
      )}
      <div className="card-body">{children}</div>
      {footer && <div className="card-footer">{footer}</div>}
    </div>
  );
}


