import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

/**
 * Browser end-to-end coverage (P12.4).
 *
 * The suite proves the real Next.js frontend ↔ FastAPI backend
 * workflow end-to-end — Server Components fetching through the
 * typed client, Server Actions mutating through it, and the
 * backend engines/repositories writing real rows — without
 * changing any application behaviour.
 *
 * Isolation contract:
 * - The FastAPI server under test runs against a disposable
 *   SQLite database (web/e2e/.e2e-adensa.db, git-ignored),
 *   created fresh by web/e2e/e2e_api_server.py via the project's
 *   canonical bootstrap and selected through the documented
 *   `DATABASE_URL=sqlite:///` seam (P5.2). The canonical
 *   development database (data/adensa.db) is never touched.
 * - No API credential exists in this mode: ADENSA_API_KEY is
 *   unset (the API's local no-credential mode) and the Next
 *   client receives no API_KEY, so there is no secret to leak
 *   into browser code — the same server-side-only discipline
 *   the application already enforces.
 * - The Next.js server is a PRODUCTION build/start (not dev):
 *   exactly the artifact CI builds and deployments run.
 *
 * Ports (3013/8013) are deliberately off the default 3000/8000
 * so the suite never collides with a developer's running stack.
 */

const API_PORT = 8013;
const WEB_PORT = 3013;
const API_BASE = `http://127.0.0.1:${API_PORT}`;
const WEB_BASE = `http://127.0.0.1:${WEB_PORT}`;

/**
 * The disposable database, deterministically located and
 * exported before the web-server commands and global setup
 * resolve their environment (config evaluation happens first).
 * Forward slashes keep the sqlite:/// URL portable.
 */
const E2E_DB_PATH = path
  .join(__dirname, "e2e", ".e2e-adensa.db")
  .replace(/\\/g, "/");

process.env.E2E_DATABASE_PATH = E2E_DB_PATH;

/** Project root and its Python interpreter (absolute: the
 * web-server command runs through the Windows shell). */
const PROJECT_ROOT = path.resolve(__dirname, "..");
const PYTHON = path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe");

/**
 * Local-only throwaway credential for the E2E stack — the same
 * X-API-Key mechanism production uses (ADR-008), scoped to a
 * loopback-only server pair over a disposable database. It is
 * a process-env value of the two local servers and never
 * reaches browser code (the API client reads it server-side
 * only). Deliberately obviously-non-secret and short.
 */
const E2E_API_KEY = "adensa-e2e-local";

export default defineConfig({
  testDir: "./e2e",
  /* All flows run against one disposable database; the spec
     file's serial mode matches the workflow's sequential nature
     (a decision is consumed by the next test). The database is
     prepared by the API web server process itself — see
     e2e/e2e_api_server.py — because Playwright starts web
     servers BEFORE global setup runs. */
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  timeout: 60_000,
  globalTimeout: 5 * 60_000,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: WEB_BASE,
    trace: "retain-on-failure",
    /* Reduced-motion respect: force the browser-level reduced
       motion preference so any motion-sensitive rendering stays
       deterministic; the application ships no entrance
       animations of its own, so no user style is needed. */
    contextOptions: {
      reducedMotion: "reduce",
    },
  },
  webServer: [
    {
      command: `"${PYTHON}" "${path.join("e2e", "e2e_api_server.py")}"`,
      url: `${API_BASE}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 180_000,
      env: {
        E2E_DATABASE_PATH: E2E_DB_PATH,
        E2E_API_PORT: String(API_PORT),
        PYTHONPATH: PROJECT_ROOT,
        ADENSA_API_KEY: E2E_API_KEY,
      },
    },
    {
      command: `npx next start -p ${WEB_PORT}`,
      url: WEB_BASE,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        API_BASE_URL: API_BASE,
        API_KEY: E2E_API_KEY,
      },
    },
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
