import { Card } from "../components/Card";

export function Tags() {
  return (
    <div className="row">
      <div className="col-12">
        <Card title="Tags, Tendencias y Filtros">
          <p className="mb-2">
            Usar endpoints de tags (creación/edición), CVT y logger para mostrar valores en tiempo
            real y tendencias (SocketIO + API).
          </p>
          <ul className="mb-0">
            <li>CRUD de tags con validaciones (sample_time, data_type, etc.).</li>
            <li>Tendencias con paginación y sample_time (usar read_tabular_data).</li>
            <li>Configuración de filtros (deadband, gaussian, detección outliers).</li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
