import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { AppProviders } from "./app/providers";
import { CapturePage } from "./pages/CapturePage";
import "./styles/globals.css";
const captureToken = window.location.pathname.match(
  /^\/capture\/([A-Za-z0-9_-]+)$/,
)?.[1];
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppProviders>
      {captureToken ? <CapturePage token={captureToken} /> : <App />}
    </AppProviders>
  </React.StrictMode>,
);
