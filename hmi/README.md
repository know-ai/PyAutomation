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

## Notas de integración

- **AdminLTE 4** se importa desde el paquete `admin-lte` y Bootstrap 5.
- **Autenticación**: endpoints `/api/users/login`, `/signup`, `/reset_password` consumidos desde `services/auth.ts`.
- **Protección de rutas**: `AppRoutes` redirige a `/login` si no hay token.
- **SocketIO**: pendiente de integrar; usar `VITE_SOCKET_IO_URL`.
- **End-points de dominio** (comunicaciones, DB, tags, alarmas, máquinas) deben conectarse a los recursos ya expuestos en `automation/modules`.
- **No se toca el backend**: toda la migración es sólo front.

## Próximos pasos

- Mapear endpoints exactos para cada módulo y completar servicios + slices específicos.
- Integrar SocketIO para tiempo real (estado OPC UA, CVT, alarmas).
- Replicar flujos de Dash en las nuevas páginas con componentes AdminLTE.
- Añadir tests (React Testing Library) y temas (light/dark).

