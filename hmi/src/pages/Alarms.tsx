import { Card } from "../components/Card";

export function Alarms() {
  return (
    <div className="row">
      <div className="col-12">
        <Card title="Alarmas">
          <p className="mb-2">
            Gestión completa de alarmas: definición, estados, sumario con paginación (usar endpoints de alarms y AlarmSummary).
          </p>
          <ul className="mb-0">
            <li>CRUD de alarmas (tipos HIGH/LOW/BOOL) y asociación a tags.</li>
            <li>Sumario con paginación (get_alarm_summary). Reconocer / Shelve / OOS.</li>
            <li>Estado en tiempo real vía SocketIO.</li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
