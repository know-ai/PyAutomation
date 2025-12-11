import { Card } from "../components/Card";

export function Dashboard() {
  return (
    <div className="row">
      <div className="col-12 col-lg-6">
        <Card title="Estado general">
          <p className="mb-0">Panel inicial con KPIs y accesos rápidos.</p>
        </Card>
      </div>
      <div className="col-12 col-lg-6">
        <Card title="Pendiente de integración">
          <ul className="mb-0">
            <li>KPIs de comunicaciones (OPCUA, conexiones activas).</li>
            <li>Resumen de alarmas (activas / reconocidas).</li>
            <li>Salud de base de datos y buffers de tags.</li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
