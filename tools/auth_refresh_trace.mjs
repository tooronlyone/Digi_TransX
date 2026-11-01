#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

function arg(name, fallback = undefined) {
  const idx = process.argv.indexOf(`--${name}`);
  if (idx >= 0 && idx + 1 < process.argv.length) return process.argv[idx + 1];
  return fallback;
}

function usage(message) {
  if (message) console.error(`ERROR: ${message}`);
  console.error(`Usage:
  node tools/auth_refresh_trace.mjs --cookies backend/scripts/seed_output/local_auth_refresh_trace.json --state A --base-url http://127.0.0.1:5173 --out traces/auth-refresh-A.json

States:
  A = A_valid_session_valid_access_proof_mpin
  B = B_valid_session_missing_access_proof_mpin
  C = C_valid_session_missing_access_proof_no_mpin
`);
  process.exit(2);
}

const stateAliases = {
  A: "A_valid_session_valid_access_proof_mpin",
  B: "B_valid_session_missing_access_proof_mpin",
  C: "C_valid_session_missing_access_proof_no_mpin",
};

const cookiesPath = arg("cookies", process.env.TRACE_COOKIES_JSON);
const stateArg = arg("state", process.env.TRACE_STATE || "A");
const baseUrl = arg("base-url", process.env.TRACE_BASE_URL || "http://127.0.0.1:5173");
const outPath = arg("out", process.env.TRACE_OUTPUT || `traces/auth-refresh-${stateArg}.json`);
const routePath = arg("path", process.env.TRACE_PATH || "/transporter/dashboard");

if (!cookiesPath) usage("Missing --cookies.");
const parsedUrl = new URL(baseUrl);
if (!["localhost", "127.0.0.1", "::1"].includes(parsedUrl.hostname)) {
  usage(`Refusing non-loopback base URL host ${parsedUrl.hostname}.`);
}

let playwright;
try {
  const imported = await import("playwright");
  playwright = imported.chromium ? imported : imported.default;
} catch (error) {
  const frontendPlaywright = path.resolve("frontend-react", "node_modules", "playwright", "index.js");
  try {
    const imported = await import(pathToFileURL(frontendPlaywright).href);
    playwright = imported.chromium ? imported : imported.default;
  } catch {
    console.error("ERROR: The playwright package is not installed for this workspace.");
    console.error("Install it only for local tracing under frontend-react, then rerun this script. Example:");
    console.error("  cd frontend-react");
    console.error("  npm install --no-save playwright");
    console.error(`Original import error: ${error.message}`);
    process.exit(2);
  }
}

const seed = JSON.parse(fs.readFileSync(cookiesPath, "utf8"));
const stateKey = stateAliases[stateArg] || stateArg;
const state = seed.states?.[stateKey];
if (!state) usage(`State ${stateArg} was not found in ${cookiesPath}.`);

const startedAt = Date.now();
const timeline = [];
const consoleErrors = [];
const authMeResponses = [];
let firstAuthMeFinishedAt = null;

function rel() {
  return Date.now() - startedAt;
}

function classifyUi(text) {
  const lower = text.toLowerCase();
  return {
    checkingSecureAccess: lower.includes("checking secure access"),
    checkingSession: lower.includes("checking session"),
    login: lower.includes("welcome back") || lower.includes("sign in") || lower.includes("login"),
    unlock: lower.includes("unlock"),
    mpin: lower.includes("mpin"),
    password: lower.includes("password"),
    dashboard: lower.includes("dashboard"),
  };
}

const browser = await playwright.chromium.launch({ headless: true });
const context = await browser.newContext({
  baseURL: baseUrl,
  ignoreHTTPSErrors: true,
});

const cookieSpecs = Object.entries(state.cookies || {}).map(([name, value]) => ({
  name,
  value,
  domain: parsedUrl.hostname,
  path: "/",
  httpOnly: true,
  secure: false,
  sameSite: "Lax",
}));
await context.addCookies(cookieSpecs);

const page = await context.newPage();

page.on("request", (request) => {
  timeline.push({
    index: timeline.length + 1,
    event: "request",
    atMs: rel(),
    method: request.method(),
    url: request.url(),
    resourceType: request.resourceType(),
    beforeAuthMeComplete: firstAuthMeFinishedAt === null,
  });
});

page.on("response", (response) => {
  const row = {
    index: timeline.length + 1,
    event: "response",
    atMs: rel(),
    status: response.status(),
    url: response.url(),
    beforeAuthMeComplete: firstAuthMeFinishedAt === null,
  };
  timeline.push(row);
  if (new URL(response.url()).pathname === "/auth/me") {
    firstAuthMeFinishedAt ??= rel();
    authMeResponses.push(row);
  }
});

page.on("console", (message) => {
  if (["error", "warning"].includes(message.type())) {
    consoleErrors.push({ atMs: rel(), type: message.type(), text: message.text() });
  }
});

page.on("pageerror", (error) => {
  consoleErrors.push({ atMs: rel(), type: "pageerror", text: error.message });
});

const targetUrl = new URL(routePath, baseUrl).toString();
let navigationError = null;
try {
  await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(1000);
} catch (error) {
  navigationError = error.message;
}

const bodyText = await page.locator("body").innerText({ timeout: 5000 }).catch(() => "");
const result = {
  capturedAt: new Date().toISOString(),
  baseUrl,
  routePath,
  state: stateKey,
  userEmail: state.email,
  navigationError,
  counts: {
    authMe: authMeResponses.length,
    responsesByStatus: timeline
      .filter((row) => row.event === "response")
      .reduce((acc, row) => {
        acc[row.status] = (acc[row.status] || 0) + 1;
        return acc;
      }, {}),
  },
  firstAuthMeFinishedAtMs: firstAuthMeFinishedAt,
  requestsBeforeAuthMeComplete: timeline.filter(
    (row) => row.event === "request" && row.beforeAuthMeComplete,
  ),
  authMeResponses,
  uiState: classifyUi(bodyText),
  visibleTextSample: bodyText.slice(0, 1200),
  consoleErrors,
  timeline,
};

await browser.close();

const absoluteOut = path.resolve(outPath);
fs.mkdirSync(path.dirname(absoluteOut), { recursive: true });
fs.writeFileSync(absoluteOut, JSON.stringify(result, null, 2));

console.log(`Trace written to ${absoluteOut}`);
console.log(`State: ${stateKey}`);
console.log(`/auth/me responses: ${authMeResponses.length}`);
console.log(`First /auth/me finished at: ${firstAuthMeFinishedAt ?? "never"} ms`);
console.log(`Statuses: ${JSON.stringify(result.counts.responsesByStatus)}`);
console.log(`UI: ${JSON.stringify(result.uiState)}`);
if (consoleErrors.length) console.log(`Console warnings/errors: ${consoleErrors.length}`);
