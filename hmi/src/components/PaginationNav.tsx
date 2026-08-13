import { useTranslation } from "../hooks/useTranslation";

type PaginationNavProps = {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  disabled?: boolean;
};

function getVisiblePages(current: number, total: number, sibling = 2): Array<number | "ellipsis"> {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  const start = Math.max(2, current - sibling);
  const end = Math.min(total - 1, current + sibling);
  const items: Array<number | "ellipsis"> = [1];

  if (start > 2) {
    items.push("ellipsis");
  }
  for (let page = start; page <= end; page += 1) {
    items.push(page);
  }
  if (end < total - 1) {
    items.push("ellipsis");
  }
  items.push(total);
  return items;
}

export function PaginationNav({
  currentPage,
  totalPages,
  onPageChange,
  disabled = false,
}: PaginationNavProps) {
  const { t } = useTranslation();

  if (totalPages <= 1) {
    return null;
  }

  const goTo = (page: number) => {
    if (disabled || page < 1 || page > totalPages || page === currentPage) {
      return;
    }
    onPageChange(page);
  };

  return (
    <nav className="pagination-nav" aria-label={t("pagination.nav")}>
      <ul className="pagination pagination-sm mb-0 flex-wrap justify-content-end">
        <li className={`page-item ${currentPage === 1 ? "disabled" : ""}`}>
          <button
            type="button"
            className="page-link"
            onClick={() => goTo(1)}
            disabled={disabled || currentPage === 1}
            aria-label={t("pagination.first")}
            title={t("pagination.first")}
          >
            <i className="bi bi-chevron-bar-left" aria-hidden="true" />
          </button>
        </li>
        <li className={`page-item ${currentPage === 1 ? "disabled" : ""}`}>
          <button
            type="button"
            className="page-link"
            onClick={() => goTo(currentPage - 1)}
            disabled={disabled || currentPage === 1}
            aria-label={t("pagination.previous")}
            title={t("pagination.previous")}
          >
            <i className="bi bi-chevron-left" aria-hidden="true" />
          </button>
        </li>
        {getVisiblePages(currentPage, totalPages).map((item, index) =>
          item === "ellipsis" ? (
            <li key={`ellipsis-${index}`} className="page-item disabled">
              <span className="page-link">…</span>
            </li>
          ) : (
            <li key={item} className={`page-item ${currentPage === item ? "active" : ""}`}>
              <button
                type="button"
                className="page-link"
                onClick={() => goTo(item)}
                disabled={disabled}
                aria-current={currentPage === item ? "page" : undefined}
              >
                {item}
              </button>
            </li>
          )
        )}
        <li className={`page-item ${currentPage === totalPages ? "disabled" : ""}`}>
          <button
            type="button"
            className="page-link"
            onClick={() => goTo(currentPage + 1)}
            disabled={disabled || currentPage === totalPages}
            aria-label={t("pagination.next")}
            title={t("pagination.next")}
          >
            <i className="bi bi-chevron-right" aria-hidden="true" />
          </button>
        </li>
        <li className={`page-item ${currentPage === totalPages ? "disabled" : ""}`}>
          <button
            type="button"
            className="page-link"
            onClick={() => goTo(totalPages)}
            disabled={disabled || currentPage === totalPages}
            aria-label={t("pagination.last")}
            title={t("pagination.last")}
          >
            <i className="bi bi-chevron-bar-right" aria-hidden="true" />
          </button>
        </li>
      </ul>
    </nav>
  );
}
