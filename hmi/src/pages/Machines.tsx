import { Card } from "../components/Card";

export function Machines() {
  return (
    <div className="row">
      <div className="col-12">
        <Card title="Machines (State Machines)">
          <p className="mb-2">
            Configuración de máquinas de estados, intervalos y modos (sync/async), reflejando lo
            disponible en las páginas Dash actuales.
          </p>
          <ul className="mb-0">
            <li>Listado de máquinas con estado actual.</li>
            <li>Configuración de intervalos y modos de ejecución.</li>
            <li>Monitoreo en tiempo real de variables asociadas.</li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
