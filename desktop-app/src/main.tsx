import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

const legalPath = window.location.pathname.replace(/\/$/, "") || "/";
if (
  legalPath === "/politicas-privacidad" ||
  legalPath === "/privacy" ||
  legalPath === "/privacy-policy"
) {
  // El SW viejo a veces sirve el SPA en esta URL; /api/* no está cacheado.
  window.location.replace("/api/legal/privacidad");
} else {
  ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}
