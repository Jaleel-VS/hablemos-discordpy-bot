import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
// Self-hosted fonts (bundled into our build, served from our own origin so
// Discord's proxy CSP doesn't block them). Silkscreen = bitmap display face
// for headings/game names/pet names only; DM Sans = everything you read.
import "@fontsource/silkscreen/400.css";
import "@fontsource/silkscreen/700.css";
import "@fontsource-variable/dm-sans";
import "./styles.css";
import { applyTheme, getTheme } from "./theme";

// Before first render so there's no flash of the wrong palette.
applyTheme(getTheme());

const root = document.getElementById("root");
if (!root) {
  throw new Error("Missing #root element");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
