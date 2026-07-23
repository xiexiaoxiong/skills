#!/usr/bin/env node

import { spawn } from "node:child_process";
import { access, mkdir, readFile, readlink, writeFile } from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import { createRequire } from "node:module";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const COMMANDS = new Set([
  "probe",
  "start",
  "status",
  "snapshot",
  "navigate",
  "click-text",
  "fill-selector",
  "stop",
]);
const DEFAULT_RUNTIME_DIR = path.join(
  process.env.XDG_CACHE_HOME || path.join(os.homedir(), ".cache"),
  "ip-proposal-playwright",
);

function parseArgs(argv) {
  const [command = "probe", ...rest] = argv;
  if (!COMMANDS.has(command)) {
    throw new Error(`Unknown command: ${command}`);
  }

  const args = { command };
  for (let i = 0; i < rest.length; i += 1) {
    const token = rest[i];
    if (!token.startsWith("--")) throw new Error(`Unexpected argument: ${token}`);
    const key = token.slice(2);
    const next = rest[i + 1];
    if (next == null || next.startsWith("--")) args[key] = true;
    else {
      args[key] = next;
      i += 1;
    }
  }
  return args;
}

function requireValue(args, key) {
  const value = args[key];
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`Missing required option --${key}`);
  }
  return value;
}

function safeHttpUrl(value) {
  const parsed = new URL(value);
  if (!new Set(["http:", "https:", "about:"]).has(parsed.protocol)) {
    throw new Error(`Unsupported URL protocol: ${parsed.protocol}`);
  }
  return parsed.toString();
}

async function executable(pathname) {
  try {
    await access(pathname, fsConstants.X_OK);
    return true;
  } catch {
    return false;
  }
}

async function findOnPath(names) {
  const searchDirs = (process.env.PATH || "").split(path.delimiter).filter(Boolean);
  for (const name of names) {
    for (const dir of searchDirs) {
      const candidate = path.join(dir, name);
      if (await executable(candidate)) return candidate;
    }
  }
  return null;
}

async function findBrowserExecutable(explicitPath) {
  if (explicitPath) {
    const resolved = path.resolve(explicitPath);
    if (!(await executable(resolved))) throw new Error(`Browser is not executable: ${resolved}`);
    return resolved;
  }

  const candidates = [];
  if (process.platform === "darwin") {
    candidates.push(
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
      "/Applications/Chromium.app/Contents/MacOS/Chromium",
    );
  } else if (process.platform === "win32") {
    for (const base of [process.env.PROGRAMFILES, process.env["PROGRAMFILES(X86)"], process.env.LOCALAPPDATA]) {
      if (!base) continue;
      candidates.push(
        path.join(base, "Google", "Chrome", "Application", "chrome.exe"),
        path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
      );
    }
  } else {
    const fromPath = await findOnPath([
      "google-chrome-stable",
      "google-chrome",
      "microsoft-edge-stable",
      "chromium-browser",
      "chromium",
    ]);
    if (fromPath) return fromPath;
  }

  for (const candidate of candidates) {
    if (await executable(candidate)) return candidate;
  }
  return null;
}

function moduleSearchDirs() {
  const dirs = [
    process.env.IP_PROPOSAL_PW_MODULE_DIR,
    path.join(process.env.IP_PROPOSAL_PW_RUNTIME_DIR || DEFAULT_RUNTIME_DIR, "node_modules"),
    path.join(process.cwd(), "node_modules"),
    path.join(path.dirname(fileURLToPath(import.meta.url)), "..", ".runtime", "node_modules"),
  ];
  return [...new Set(dirs.filter(Boolean).map((value) => path.resolve(value)))];
}

function loadPlaywright() {
  const failures = [];
  for (const dir of moduleSearchDirs()) {
    const scopedRequire = createRequire(path.join(dir, "ip-proposal-playwright-loader.cjs"));
    for (const packageName of ["playwright-core", "playwright"]) {
      try {
        return { playwright: scopedRequire(packageName), packageName, moduleDir: dir };
      } catch (error) {
        failures.push(`${packageName}@${dir}: ${error.code || error.message}`);
      }
    }
  }
  const error = new Error("Playwright is not installed in a known runtime directory");
  error.failures = failures;
  throw error;
}

function assertTaskProfileDir(profileDir) {
  const resolved = path.resolve(profileDir);
  const homeDir = path.resolve(os.homedir());
  const forbidden = new Set([path.parse(resolved).root, homeDir, path.dirname(homeDir)]);
  if (forbidden.has(resolved)) throw new Error(`Refusing broad profile directory: ${resolved}`);
  const normalized = resolved.replaceAll("\\", "/").toLowerCase();
  if (normalized.includes("/library/application support/google/chrome")) {
    throw new Error("Refusing the user's normal Chrome profile; use a task-specific profile directory");
  }
  return resolved;
}

async function allocatePort() {
  return await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : null;
      server.close((error) => (error ? reject(error) : resolve(port)));
    });
  });
}

async function cdpHealthy(port) {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/json/version`, {
      signal: AbortSignal.timeout(1500),
    });
    return response.ok;
  } catch {
    return false;
  }
}

async function waitForCdp(port, timeoutMs = 45000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await cdpHealthy(port)) return;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Chrome CDP endpoint did not become ready on 127.0.0.1:${port}`);
}

function macAppPath(browserPath) {
  const marker = ".app/Contents/MacOS/";
  const index = browserPath.indexOf(marker);
  return index === -1 ? null : browserPath.slice(0, index + 4);
}

async function launchVisibleBrowser(browserPath, chromeArgs, profileDir) {
  const appPath = process.platform === "darwin" ? macAppPath(browserPath) : null;
  if (appPath) {
    const launcher = spawn("/usr/bin/open", ["-na", appPath, "--args", ...chromeArgs], {
      stdio: "ignore",
    });
    await new Promise((resolve, reject) => {
      launcher.once("error", reject);
      launcher.once("exit", (code) => {
        if (code === 0) resolve();
        else reject(new Error(`macOS open launcher exited with code ${code}`));
      });
    });
    return { launcherPid: launcher.pid, browserPid: null, launchStrategy: "macos-launch-services" };
  }

  const child = spawn(browserPath, chromeArgs, { detached: true, stdio: "ignore" });
  child.unref();
  return { launcherPid: null, browserPid: child.pid, launchStrategy: "detached-process" };
}

async function resolveBrowserPid(profileDir, fallbackPid) {
  try {
    const target = await readlink(path.join(profileDir, "SingletonLock"));
    const match = target.match(/-(\d+)$/);
    if (match) return Number(match[1]);
  } catch {
    // Chrome may not expose a SingletonLock on every platform.
  }
  return fallbackPid;
}

async function readState(stateFile) {
  return JSON.parse(await readFile(path.resolve(stateFile), "utf8"));
}

async function writeState(stateFile, state) {
  const resolved = path.resolve(stateFile);
  await mkdir(path.dirname(resolved), { recursive: true });
  await writeFile(resolved, `${JSON.stringify(state, null, 2)}\n`, "utf8");
  return resolved;
}

async function connectToState(state) {
  const { playwright, packageName, moduleDir } = loadPlaywright();
  const browser = await playwright.chromium.connectOverCDP(state.cdpUrl);
  return { browser, packageName, moduleDir };
}

function selectPage(browser, preferredHost) {
  const pages = browser.contexts().flatMap((context) => context.pages());
  const viable = pages.filter((page) => !page.url().startsWith("devtools://"));
  if (preferredHost) {
    const matched = viable.findLast((page) => {
      try {
        return new URL(page.url()).host === preferredHost;
      } catch {
        return false;
      }
    });
    if (matched) return matched;
  }
  return viable.findLast((page) => page.url() !== "about:blank") || viable.at(-1) || null;
}

async function capture(browser, state, label = "snapshot", pageHost = null) {
  const preferredHost = pageHost || (state.targetUrl ? new URL(state.targetUrl).host : null);
  const page = selectPage(browser, preferredHost);
  if (!page) throw new Error("No inspectable page found in the persistent browser");

  const timestamp = new Date().toISOString().replaceAll(":", "-");
  const evidenceDir = path.resolve(state.evidenceDir);
  await mkdir(evidenceDir, { recursive: true });
  const screenshotPath = path.join(evidenceDir, `${timestamp}_${label}.png`);
  const capturePath = path.join(evidenceDir, `${timestamp}_${label}.json`);

  const title = await page.title().catch(() => "");
  const url = page.url();
  const visibleText = await page.locator("body").innerText({ timeout: 10000 }).catch(() => "");
  await page.screenshot({ path: screenshotPath, fullPage: false });

  const record = {
    capturedAt: new Date().toISOString(),
    label,
    title,
    url,
    screenshotPath,
    visibleText: visibleText.slice(0, 50000),
  };
  await writeFile(capturePath, `${JSON.stringify(record, null, 2)}\n`, "utf8");
  return { ...record, capturePath, visibleTextLength: visibleText.length };
}

async function probe(args) {
  const browserPath = await findBrowserExecutable(args["browser-path"]);
  let playwrightInfo = null;
  let playwrightError = null;
  try {
    const loaded = loadPlaywright();
    playwrightInfo = { packageName: loaded.packageName, moduleDir: loaded.moduleDir };
  } catch (error) {
    playwrightError = error.message;
  }
  return {
    ready: Boolean(browserPath && playwrightInfo),
    node: process.version,
    platform: process.platform,
    displayAvailable: process.platform !== "linux" || Boolean(process.env.DISPLAY || process.env.WAYLAND_DISPLAY),
    browserPath,
    playwright: playwrightInfo,
    playwrightError,
    runtimeDir: process.env.IP_PROPOSAL_PW_RUNTIME_DIR || DEFAULT_RUNTIME_DIR,
    moduleSearchDirs: moduleSearchDirs(),
  };
}

async function start(args) {
  loadPlaywright();
  const targetUrl = safeHttpUrl(requireValue(args, "url"));
  const profileDir = assertTaskProfileDir(requireValue(args, "profile-dir"));
  const evidenceDir = path.resolve(requireValue(args, "evidence-dir"));
  const stateFile = path.resolve(args["state-file"] || `${profileDir}.handoff.json`);
  const browserPath = await findBrowserExecutable(args["browser-path"]);
  if (!browserPath) throw new Error("No supported local Chrome/Edge/Chromium executable found");

  try {
    const existing = await readState(stateFile);
    if (existing.port && (await cdpHealthy(existing.port))) {
      return { reused: true, stateFile, ...existing };
    }
  } catch {
    // No reusable state.
  }

  await mkdir(profileDir, { recursive: true });
  await mkdir(evidenceDir, { recursive: true });
  const port = args.port ? Number(args.port) : await allocatePort();
  if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error(`Invalid port: ${args.port}`);

  const chromeArgs = [
    `--remote-debugging-address=127.0.0.1`,
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--new-window",
    targetUrl,
  ];
  const launched = await launchVisibleBrowser(browserPath, chromeArgs, profileDir);
  const startupTimeoutMs = args["startup-timeout-ms"] ? Number(args["startup-timeout-ms"]) : 45000;
  if (!Number.isInteger(startupTimeoutMs) || startupTimeoutMs < 5000 || startupTimeoutMs > 120000) {
    throw new Error(`Invalid startup timeout: ${args["startup-timeout-ms"]}`);
  }
  await waitForCdp(port, startupTimeoutMs);
  const browserPid = await resolveBrowserPid(profileDir, launched.browserPid);

  const state = {
    version: 1,
    pid: browserPid,
    launcherPid: launched.launcherPid,
    launchStrategy: launched.launchStrategy,
    port,
    cdpUrl: `http://127.0.0.1:${port}`,
    browserPath,
    profileDir,
    evidenceDir,
    targetUrl,
    startedAt: new Date().toISOString(),
    status: "visible-persistent-browser-ready",
  };
  await writeState(stateFile, state);
  const { browser, packageName, moduleDir } = await connectToState(state);
  const preLogin = await capture(browser, state, "pre-login");
  return { reused: false, stateFile, packageName, moduleDir, ...state, preLogin };
}

async function status(args) {
  const stateFile = path.resolve(requireValue(args, "state-file"));
  const state = await readState(stateFile);
  const healthy = await cdpHealthy(state.port);
  if (!healthy) return { stateFile, healthy: false, ...state };
  const { browser, packageName, moduleDir } = await connectToState(state);
  const pages = browser.contexts().flatMap((context) => context.pages()).map((page) => ({
    title: "",
    url: page.url(),
  }));
  for (const [index, page] of browser.contexts().flatMap((context) => context.pages()).entries()) {
    pages[index].title = await page.title().catch(() => "");
  }
  return { stateFile, healthy: true, packageName, moduleDir, pages, ...state };
}

async function snapshot(args) {
  const stateFile = path.resolve(requireValue(args, "state-file"));
  const state = await readState(stateFile);
  if (!(await cdpHealthy(state.port))) throw new Error("Persistent browser is not reachable");
  const { browser, packageName, moduleDir } = await connectToState(state);
  const record = await capture(browser, state, args.label || "post-login", args["page-host"] || null);
  return { stateFile, packageName, moduleDir, ...record };
}

async function navigate(args) {
  const stateFile = path.resolve(requireValue(args, "state-file"));
  const targetUrl = safeHttpUrl(requireValue(args, "url"));
  const state = await readState(stateFile);
  if (!(await cdpHealthy(state.port))) throw new Error("Persistent browser is not reachable");
  const { browser, packageName, moduleDir } = await connectToState(state);
  const context = browser.contexts()[0];
  const page = selectPage(browser, args["page-host"] || null) || (await context.newPage());
  await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: Number(args.timeout || 30000) });
  state.targetUrl = targetUrl;
  state.lastNavigatedAt = new Date().toISOString();
  await writeState(stateFile, state);
  const record = await capture(browser, state, args.label || "navigate");
  return { stateFile, packageName, moduleDir, ...record };
}

async function clickText(args) {
  const stateFile = path.resolve(requireValue(args, "state-file"));
  const text = requireValue(args, "text");
  const state = await readState(stateFile);
  if (!(await cdpHealthy(state.port))) throw new Error("Persistent browser is not reachable");
  const { browser, packageName, moduleDir } = await connectToState(state);
  const pageHost = args["page-host"] || (state.targetUrl ? new URL(state.targetUrl).host : null);
  const page = selectPage(browser, pageHost);
  if (!page) throw new Error("No inspectable page found in the persistent browser");

  const locator = page.getByText(text, { exact: args.exact !== "false" });
  const count = await locator.count();
  if (count === 0) throw new Error(`No visible text target found: ${text}`);
  await locator.last().click({ timeout: Number(args.timeout || 10000) });
  await page.waitForTimeout(Number(args["wait-after-ms"] || 1500));
  const record = await capture(browser, state, args.label || "click-text", pageHost);
  return { stateFile, packageName, moduleDir, clickedText: text, matchedCount: count, ...record };
}

async function fillSelector(args) {
  const stateFile = path.resolve(requireValue(args, "state-file"));
  const selector = requireValue(args, "selector");
  const value = requireValue(args, "value");
  const state = await readState(stateFile);
  if (!(await cdpHealthy(state.port))) throw new Error("Persistent browser is not reachable");
  const { browser, packageName, moduleDir } = await connectToState(state);
  const pageHost = args["page-host"] || (state.targetUrl ? new URL(state.targetUrl).host : null);
  const page = selectPage(browser, pageHost);
  if (!page) throw new Error("No inspectable page found in the persistent browser");

  const locator = page.locator(selector);
  const count = await locator.count();
  if (count === 0) throw new Error(`No selector target found: ${selector}`);
  await locator.last().fill(value, { timeout: Number(args.timeout || 10000) });
  await page.waitForTimeout(Number(args["wait-after-ms"] || 500));
  const record = await capture(browser, state, args.label || "fill-selector", pageHost);
  return { stateFile, packageName, moduleDir, selector, matchedCount: count, ...record };
}

async function stop(args) {
  const stateFile = path.resolve(requireValue(args, "state-file"));
  const state = await readState(stateFile);
  if (state.pid && Number.isInteger(state.pid)) {
    try {
      process.kill(state.pid, "SIGTERM");
    } catch (error) {
      if (error.code !== "ESRCH") throw error;
    }
  }
  state.status = "stopped";
  state.stoppedAt = new Date().toISOString();
  await writeState(stateFile, state);
  return { stateFile, stopped: true, pid: state.pid };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const handlers = {
    probe,
    start,
    status,
    snapshot,
    navigate,
    "click-text": clickText,
    "fill-selector": fillSelector,
    stop,
  };
  const result = await handlers[args.command](args);
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    process.stderr.write(`${JSON.stringify({ error: error.message, command: process.argv[2] || "probe" }, null, 2)}\n`);
    process.exit(1);
  });
