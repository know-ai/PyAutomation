import { useTranslation } from "../hooks/useTranslation";

export function NoAccess() {
  const { t } = useTranslation();
  return (
    <div className="p-4">
      <div className="alert alert-warning mb-0" role="alert">
        {t("authz.noAccess")}
      </div>
    </div>
  );
}
