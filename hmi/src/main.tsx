import React from "react";
import ReactDOM from "react-dom/client";
import { Provider } from "react-redux";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { store } from "./store/store";
import "./styles/global.css";
import "admin-lte/dist/js/adminlte.min.js";

// Obtener el base path desde la variable de entorno de Vite o usar /hmi por defecto
const basePath = import.meta.env.VITE_BASE_PATH || "/hmi/";
// Normalizar el base path (remover trailing slash para BrowserRouter)
const basename = basePath.endsWith("/") ? basePath.slice(0, -1) : basePath;

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <Provider store={store}>
      <BrowserRouter basename={basename}>
        <App />
      </BrowserRouter>
    </Provider>
  </React.StrictMode>
);


