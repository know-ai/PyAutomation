import { Card } from "../components/Card";
import { useTranslation } from "../hooks/useTranslation";

export function Database() {
  const { t } = useTranslation();
  return (
    <div className="row">
      <div className="col-12">
        <Card title={t("navigation.database")}>
          <p className="mb-2">
            {t("database.description")}
          </p>
          <ul className="mb-0">
            <li>{t("database.feature1")}</li>
            <li>{t("database.feature2")}</li>
            <li>{t("database.feature3")}</li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
