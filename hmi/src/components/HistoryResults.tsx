import type { PropsWithChildren } from "react";
import clsx from "clsx";

type HistoryResultsProps = PropsWithChildren<{
  loading: boolean;
  hasLoaded: boolean;
  loadingLabel: string;
}>;

export function HistoryResults({
  loading,
  hasLoaded,
  loadingLabel,
  children,
}: HistoryResultsProps) {
  if (!hasLoaded && loading) {
    return (
      <div className="text-center py-4">
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">{loadingLabel}</span>
        </div>
      </div>
    );
  }

  return (
    <div className={clsx("history-results", loading && "history-results--refreshing")}>
      {loading && (
        <div className="history-results__badge" role="status" aria-live="polite">
          <span className="spinner-border spinner-border-sm" aria-hidden="true" />
          <span className="visually-hidden">{loadingLabel}</span>
        </div>
      )}
      {children}
    </div>
  );
}
