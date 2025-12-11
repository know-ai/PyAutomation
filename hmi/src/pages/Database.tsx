import { Card } from "../components/Card";

export function Database() {
  return (
    <div className="row">
      <div className="col-12">
        <Card title="Database">
          <p className="mb-2">
            Configuración de conexión a base de datos (PostgreSQL/MySQL/SQLite) usando endpoints
            existentes.
          </p>
          <ul className="mb-0">
            <li>Form de credenciales y prueba de conexión.</li>
            <li>Estado de conexión y reconexión.</li>
            <li>Export/Import de configuración (ya soportado por backend).</li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
