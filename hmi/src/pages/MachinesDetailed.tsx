import { Card } from "../components/Card";
import { useTranslation } from "../hooks/useTranslation";

export function MachinesDetailed() {
  const { t } = useTranslation();

  return (
    <div className="row">
      <div className="col-12">
        <Card title={t("navigation.machinesDetailed")}>
          <div className="text-center py-5">
            <p className="text-muted">{t("machines.comingSoon")}</p>
          </div>
        </Card>
      </div>
    </div>
  );
}

