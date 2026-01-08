# PyAutomation HMI (React + Redux + AdminLTE)

Front-end moderno para reemplazar gradualmente las vistas Dash de `automation/pages`, sin eliminar la funcionalidad existente mientras se completa la migración.

## Estructura

```
my-app/
├── public/
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── assets/
│   ├── components/
│   ├── pages/
│   ├── layouts/
│   ├── store/ (Redux Toolkit)
│   ├── hooks/
│   ├── services/ (axios + API)
│   ├── utils/
│   ├── routes/
│   ├── styles/ (AdminLTE + global)
│   └── config/
├── package.json
├── tsconfig.json
├── vite.config.ts
└── index.html
```

## Scripts

```bash
cd hmi/my-app
npm install
npm run dev     # modo desarrollo
npm run build   # build producción
npm run preview # servir build
```

## Configuración de Variables de Entorno

El HMI detecta automáticamente si debe usar HTTP o HTTPS basándose en las siguientes variables de entorno (en orden de prioridad):

### Variables de Entorno Disponibles

1. **`VITE_API_BASE_URL`**: URL completa de la API (incluyendo protocolo)
   ```bash
   VITE_API_BASE_URL=https://localhost:8050/api
   # o
   VITE_API_BASE_URL=http://localhost:8050/api
   ```

2. **`VITE_USE_HTTPS`**: Forzar uso de HTTPS (booleano)
   ```bash
   VITE_USE_HTTPS=true
   ```

3. **`VITE_API_HOST`**: Host y puerto del backend (sin protocolo)
   ```bash
   VITE_API_HOST=localhost:8050
   ```

4. **`VITE_SOCKET_IO_URL`**: URL completa de Socket.IO (opcional, se detecta automáticamente)
   ```bash
   VITE_SOCKET_IO_URL=https://localhost:8050
   ```

### Detección Automática

Si no se especifican variables de entorno, el sistema detecta automáticamente:

1. **Protocolo de la página actual**: Si la página se carga con HTTPS, usa HTTPS para las peticiones
2. **Fallback**: HTTP por defecto (`http://localhost:8050`)

### Certificados Autofirmados

Cuando se usan certificados autofirmados con HTTPS:

- **Primera vez**: El navegador mostrará una advertencia de seguridad. El usuario debe aceptar el certificado manualmente.
- **Después**: El navegador recordará la excepción y las peticiones funcionarán normalmente.
- **Desarrollo**: Para desarrollo local, puedes usar `VITE_USE_HTTPS=true` para forzar HTTPS.

### Ejemplo de Configuración

**Para desarrollo con HTTPS y certificados autofirmados:**
```bash
# .env
VITE_USE_HTTPS=true
VITE_API_HOST=localhost:8050
```

**Para producción:**
```bash
# .env.production
VITE_API_BASE_URL=https://api.tudominio.com/api
VITE_SOCKET_IO_URL=https://api.tudominio.com
```

## Notas de integración

- **AdminLTE 4** se importa desde el paquete `admin-lte` y Bootstrap 5.
- **Autenticación**: endpoints `/api/users/login`, `/signup`, `/reset_password` consumidos desde `services/auth.ts`.
- **Protección de rutas**: `AppRoutes` redirige a `/login` si no hay token.
- **SocketIO**: Configurado automáticamente usando `VITE_SOCKET_IO_URL` o detectado desde la configuración de la API.
- **End-points de dominio** (comunicaciones, DB, tags, alarmas, máquinas) deben conectarse a los recursos ya expuestos en `automation/modules`.
- **No se toca el backend**: toda la migración es sólo front.

## Próximos pasos

- Mapear endpoints exactos para cada módulo y completar servicios + slices específicos.
- Integrar SocketIO para tiempo real (estado OPC UA, CVT, alarmas).
- Replicar flujos de Dash en las nuevas páginas con componentes AdminLTE.
- Añadir tests (React Testing Library) y temas (light/dark).

