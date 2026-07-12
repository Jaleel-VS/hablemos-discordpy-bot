import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
// Self-hosted fonts (bundled into our build, served from our own origin so
// Discord's proxy CSP doesn't block them). Fraunces = display/wordmark,
// Space Grotesk = tiles + keyboard + UI.
import "@fontsource-variable/fraunces";
import "@fontsource-variable/space-grotesk";
import "./styles.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("Missing #root element");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
