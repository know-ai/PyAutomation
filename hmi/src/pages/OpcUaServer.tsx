import { Card } from "../components/Card";
import { useTranslation } from "../hooks/useTranslation";

export function OpcUaServer() {
  const { t } = useTranslation();

  return (
    <div className="row">
      <div className="col-12">
        <Card title={t("communications.opcuaServer")}>
          <div className="text-center py-5">
            <i className="bi bi-server" style={{ fontSize: "4rem", color: "#6c757d" }}></i>
            <h4 className="mt-3 text-muted">{t("communications.opcuaServer")}</h4>
            <p className="text-muted">{t("communications.opcuaServerPlaceholder")}</p>
          </div>
        </Card>
      </div>
    </div>
  );
}

