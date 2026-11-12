import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

// Frische Datenbank je Lauf; der Server liefert das gebaute Frontend aus (npm run build vorher)
const dataDir = path.resolve("test-results", `daten-${Date.now()}`);
const python =
  process.env.PYTHON ?? path.resolve("..", "backend", ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");

export default defineConfig({
  testDir: "tests",
  timeout: 30_000,
  workers: 1,
  reporter: [["list"]],
  use: {
    ...devices["Pixel 7"],
    baseURL: "http://127.0.0.1:8765",
    locale: "de-DE",
    timezoneId: "Europe/Berlin",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `"${python}" -m delikatessen.cli serve --host 127.0.0.1 --port 8765`,
      url: "http://127.0.0.1:8765/api/v1/status",
      reuseExistingServer: false,
      env: {
        DELIKATESSEN_DATA_DIR: dataDir,
        DELIKATESSEN_FRONTEND_DIR: path.resolve("dist"),
        // nur für den Test: Rezeptseiten kommen vom lokalen Testserver
        DELIKATESSEN_ALLOW_PRIVATE_FETCH: "true",
        DELIKATESSEN_SECRET_KEY: "nur-fuer-tests",
        // KI über eine Attrappe des Gateways, es wird keine echte KI aufgerufen
        DELIKATESSEN_KI_BASE_URL: "http://127.0.0.1:8767",
        DELIKATESSEN_KI_API_KEY: "sk-test",
      },
    },
    {
      command: `"${python}" tests/fake-ki-gateway.py 8767`,
      url: "http://127.0.0.1:8767/health",
      reuseExistingServer: false,
    },
    {
      command: `"${python}" -m http.server 8766 --bind 127.0.0.1 --directory ../backend/tests/fixtures`,
      url: "http://127.0.0.1:8766/rezeptseiten/01_einfach.html",
      reuseExistingServer: false,
    },
  ],
});
