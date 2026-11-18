const vscode = require("vscode");
const cp = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const DEFAULT_CONFIG = {
  x: 1400,
  y: 30,
  width: 560,
  expanded_height: 380,
  auto_start: true,
  auto_close_with_ide: true,
  always_on_top: true,
  window_opacity: 100,
  show_quota_ring: true,
  show_duration_timer: true,
  show_model_badge: true,
  show_diff_stats: true,
  show_bg_process: true,
  show_completion_summary: true,
  marquee_speed: 2,
  model_badge_duration_ms: 4500,
  summary_duration_ms: 6500,
  cmd_glance_duration_ms: 6000,
  poll_interval_active_ms: 320
};

let overlayChildProcess = null;
let statusBarItem = null;
let sidebarProvider = null;
let statusPollTimer = null;
let cachedRuntime = null;
let setupPromise = null;

function resolveAppDir() {
  const vsCfg = vscode.workspace.getConfiguration("antigravityTaskOverlay");
  const configuredDir = (vsCfg.get("appDirectory", "") || "").trim();
  if (configuredDir && fs.existsSync(path.join(configuredDir, "main.py"))) {
    return configuredDir;
  }
  const bundledPythonDir = path.join(__dirname, "python");
  if (fs.existsSync(path.join(bundledPythonDir, "main.py"))) {
    return bundledPythonDir;
  }
  if (fs.existsSync(path.join(__dirname, "main.py"))) {
    return __dirname;
  }
  return bundledPythonDir;
}

function getDataDir() {
  const envDir = (process.env.TASK_OVERLAY_DATA_DIR || "").trim();
  const dataDir = envDir || path.join(os.homedir(), ".antigravity-task-overlay");
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }
  // Migrasi satu kali config.json lama dari appDir jika dataDir masih kosong
  const targetCfg = path.join(dataDir, "config.json");
  if (!fs.existsSync(targetCfg)) {
    const legacyCfg = path.join(resolveAppDir(), "config.json");
    if (fs.existsSync(legacyCfg)) {
      try {
        fs.copyFileSync(legacyCfg, targetCfg);
      } catch (_) {}
    }
  }
  return dataDir;
}

function getConfigPath() {
  return path.join(getDataDir(), "config.json");
}

function getPidPath() {
  return path.join(getDataDir(), "overlay.pid");
}

function readOverlayConfig() {
  const cfgPath = getConfigPath();
  let merged = { ...DEFAULT_CONFIG };
  if (fs.existsSync(cfgPath)) {
    try {
      const raw = fs.readFileSync(cfgPath, "utf-8");
      const parsed = JSON.parse(raw);
      merged = { ...merged, ...parsed };
    } catch (_) {
      // Abaikan jika file sedang ditulis sesaat
    }
  }
  return merged;
}

function writeOverlayConfig(partialUpdate) {
  const cfgPath = getConfigPath();
  const current = readOverlayConfig();
  const updated = { ...current, ...partialUpdate };
  try {
    fs.writeFileSync(cfgPath, JSON.stringify(updated, null, 2), "utf-8");
  } catch (err) {
    vscode.window.showErrorMessage(`Gagal menyimpan konfigurasi Task Overlay: ${err.message}`);
  }
  return updated;
}

function isPidAlive(pid) {
  if (!pid || typeof pid !== "number" || pid <= 0) {
    return false;
  }
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return err && err.code === "EPERM";
  }
}

function getRunningOverlayPid() {
  const pidFile = getPidPath();
  if (fs.existsSync(pidFile)) {
    try {
      const pid = parseInt(fs.readFileSync(pidFile, "utf-8").trim(), 10);
      if (isPidAlive(pid)) {
        return pid;
      }
    } catch (_) {}
  }
  if (overlayChildProcess && overlayChildProcess.pid && isPidAlive(overlayChildProcess.pid)) {
    return overlayChildProcess.pid;
  }
  return null;
}

function execFileAsync(command, args, options = {}) {
  return new Promise((resolve) => {
    cp.execFile(
      command,
      args,
      { windowsHide: true, timeout: 10000, ...options },
      (error, stdout, stderr) => {
        resolve({
          ok: !error,
          stdout: (stdout || "").trim(),
          stderr: (stderr || "").trim(),
          error
        });
      }
    );
  });
}

async function canImportPyQt6(command, prefixArgs = []) {
  const res = await execFileAsync(command, [...prefixArgs, "-c", "import PyQt6"], { timeout: 7000 });
  return res.ok;
}

async function resolveWindowlessExec(command, prefixArgs = []) {
  const res = await execFileAsync(
    command,
    [...prefixArgs, "-c", "import sys; print(sys.executable)"],
    { timeout: 5000 }
  );
  const sysExe = res.ok && res.stdout ? res.stdout.split(/\r?\n/)[0].trim() : command;
  if (process.platform === "win32" && sysExe.toLowerCase().endsWith("python.exe")) {
    const pywPath = path.join(path.dirname(sysExe), "pythonw.exe");
    if (fs.existsSync(pywPath)) {
      return { runExec: pywPath, cliExec: sysExe, prefixArgs: [] };
    }
  }
  return { runExec: sysExe, cliExec: sysExe, prefixArgs: res.ok ? [] : prefixArgs };
}

function getManagedVenvPaths() {
  const venvDir = path.join(getDataDir(), "venv");
  if (process.platform === "win32") {
    const cliExec = path.join(venvDir, "Scripts", "python.exe");
    const pywExec = path.join(venvDir, "Scripts", "pythonw.exe");
    return {
      venvDir,
      cliExec,
      runExec: fs.existsSync(pywExec) ? pywExec : cliExec
    };
  }
  const py3 = path.join(venvDir, "bin", "python3");
  const py = path.join(venvDir, "bin", "python");
  const cliExec = fs.existsSync(py3) ? py3 : py;
  return { venvDir, cliExec, runExec: cliExec };
}

async function findSystemPython() {
  const candidates = process.platform === "win32"
    ? [
        { cmd: "python", args: [] },
        { cmd: "py", args: ["-3"] },
        { cmd: "python3", args: [] }
      ]
    : [
        { cmd: "python3", args: [] },
        { cmd: "python", args: [] }
      ];

  if (process.platform === "win32") {
    const localPyRoot = path.join(process.env.LOCALAPPDATA || "", "Programs", "Python");
    if (fs.existsSync(localPyRoot)) {
      try {
        for (const entry of fs.readdirSync(localPyRoot)) {
          const exe = path.join(localPyRoot, entry, "python.exe");
          if (fs.existsSync(exe)) {
            candidates.push({ cmd: exe, args: [] });
          }
        }
      } catch (_) {}
    }
  }

  for (const cand of candidates) {
    const res = await execFileAsync(
      cand.cmd,
      [...cand.args, "-c", "import sys; assert sys.version_info >= (3, 9)"],
      { timeout: 5000 }
    );
    if (res.ok) {
      return cand;
    }
  }
  return null;
}

async function ensureVenvWithPyQt6(sysPy, appDir) {
  if (setupPromise) {
    return setupPromise;
  }

  setupPromise = vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "Antigravity Task Overlay",
      cancellable: false
    },
    async (progress) => {
      const venv = getManagedVenvPaths();
      if (!fs.existsSync(venv.cliExec)) {
        progress.report({ message: "Membuat virtual environment Python..." });
        const venvRes = await execFileAsync(
          sysPy.cmd,
          [...sysPy.args, "-m", "venv", venv.venvDir],
          { timeout: 60000 }
        );
        if (!venvRes.ok) {
          throw new Error(venvRes.stderr || venvRes.error?.message || "Gagal membuat venv Python.");
        }
      }

      const reqPath = path.join(appDir, "requirements.txt");
      const pipArgs = fs.existsSync(reqPath)
        ? ["-m", "pip", "install", "--disable-pip-version-check", "-r", reqPath]
        : ["-m", "pip", "install", "--disable-pip-version-check", "PyQt6>=6.5.0"];

      progress.report({ message: "Memasang PyQt6 (hanya saat pertama kali dijalankan)..." });
      const pipRes = await execFileAsync(venv.cliExec, pipArgs, { timeout: 180000 });
      if (!pipRes.ok) {
        throw new Error(pipRes.stderr || pipRes.error?.message || "Gagal memasang PyQt6 via pip.");
      }

      if (!(await canImportPyQt6(venv.cliExec))) {
        throw new Error("PyQt6 berhasil dipasang tetapi gagal diimpor.");
      }

      const refreshed = getManagedVenvPaths();
      return { runExec: refreshed.runExec, cliExec: refreshed.cliExec, prefixArgs: [] };
    }
  );

  try {
    return await setupPromise;
  } finally {
    setupPromise = null;
  }
}

async function resolvePythonRuntime(appDir, interactive = true) {
  if (cachedRuntime && fs.existsSync(cachedRuntime.runExec)) {
    return cachedRuntime;
  }

  const vsCfg = vscode.workspace.getConfiguration("antigravityTaskOverlay");
  const customExec = (vsCfg.get("pythonExecutable", "") || "").trim();
  const autoSetup = vsCfg.get("autoSetupEnvironment", true);

  // 1. Jika user mengatur executable Python kustom secara eksplisit
  if (customExec && customExec !== "pythonw") {
    if (await canImportPyQt6(customExec)) {
      cachedRuntime = await resolveWindowlessExec(customExec);
      return cachedRuntime;
    }
    if (interactive) {
      const action = await vscode.window.showErrorMessage(
        `Executable Python kustom "${customExec}" tidak ditemukan atau belum memiliki PyQt6.`,
        "Buka Pengaturan"
      );
      if (action === "Buka Pengaturan") {
        vscode.commands.executeCommand("workbench.action.openSettings", "antigravityTaskOverlay.pythonExecutable");
      }
    }
    return null;
  }

  // 2. Cek managed venv di ~/.antigravity-task-overlay/venv
  const venv = getManagedVenvPaths();
  if (fs.existsSync(venv.cliExec) && (await canImportPyQt6(venv.cliExec))) {
    cachedRuntime = { runExec: venv.runExec, cliExec: venv.cliExec, prefixArgs: [] };
    return cachedRuntime;
  }

  // 3. Cek Python sistem
  const sysPy = await findSystemPython();
  if (!sysPy) {
    if (interactive) {
      const choice = await vscode.window.showErrorMessage(
        "Python 3 (>= 3.9) tidak ditemukan. Antigravity Task Overlay memerlukan Python 3 untuk berjalan.",
        "Download Python",
        "Pengaturan"
      );
      if (choice === "Download Python") {
        vscode.env.openExternal(vscode.Uri.parse("https://www.python.org/downloads/"));
      } else if (choice === "Pengaturan") {
        vscode.commands.executeCommand("workbench.action.openSettings", "antigravityTaskOverlay.pythonExecutable");
      }
    }
    return null;
  }

  // Jika Python sistem sudah punya PyQt6, pakai langsung tanpa perlu bikin venv
  if (await canImportPyQt6(sysPy.cmd, sysPy.args)) {
    cachedRuntime = await resolveWindowlessExec(sysPy.cmd, sysPy.args);
    return cachedRuntime;
  }

  // 4. Auto-setup venv + PyQt6
  if (!autoSetup) {
    if (interactive) {
      vscode.window.showErrorMessage(
        "PyQt6 belum terpasang. Jalankan `pip install PyQt6` atau aktifkan setting `antigravityTaskOverlay.autoSetupEnvironment`."
      );
    }
    return null;
  }

  try {
    cachedRuntime = await ensureVenvWithPyQt6(sysPy, appDir);
    return cachedRuntime;
  } catch (err) {
    if (interactive) {
      const retry = await vscode.window.showErrorMessage(
        `Gagal menyiapkan environment PyQt6: ${err.message}`,
        "Coba Lagi"
      );
      if (retry === "Coba Lagi") {
        return resolvePythonRuntime(appDir, true);
      }
    }
    return null;
  }
}

async function startOverlay(silent = false) {
  const appDir = resolveAppDir();
  const mainPy = path.join(appDir, "main.py");
  if (!fs.existsSync(mainPy)) {
    vscode.window.showErrorMessage(`File main.py tidak ditemukan di: ${mainPy}`);
    return;
  }

  const existingPid = getRunningOverlayPid();
  if (existingPid) {
    if (!silent) {
      vscode.window.showInformationMessage(`Antigravity Task Overlay sudah berjalan (PID: ${existingPid}).`);
    }
    updateStatusUI();
    return;
  }

  const runtime = await resolvePythonRuntime(appDir, true);
  if (!runtime) {
    updateStatusUI();
    return;
  }

  const dataDir = getDataDir();
  const cfg = readOverlayConfig();
  const args = [...runtime.prefixArgs, mainPy, "--data-dir", dataDir];
  if (cfg.auto_close_with_ide !== false) {
    args.push("--parent-pid", String(process.pid));
  }

  try {
    const child = cp.spawn(runtime.runExec, args, {
      cwd: appDir,
      detached: true,
      stdio: "ignore",
      windowsHide: true,
      env: { ...process.env, TASK_OVERLAY_DATA_DIR: dataDir }
    });

    child.on("error", (err) => {
      cachedRuntime = null;
      vscode.window.showErrorMessage(`Gagal menjalankan Task Overlay: ${err.message}`);
    });

    child.unref();
    overlayChildProcess = child;

    setTimeout(() => {
      updateStatusUI();
    }, 600);

    if (!silent) {
      vscode.window.showInformationMessage("Antigravity Task Overlay dijalankan.");
    }
  } catch (err) {
    vscode.window.showErrorMessage(`Gagal menjalankan Task Overlay: ${err.message}`);
  }
}

function stopOverlay(silent = false) {
  const appDir = resolveAppDir();
  const dataDir = getDataDir();
  const mainPy = path.join(appDir, "main.py");
  const pid = getRunningOverlayPid();
  const pidFile = getPidPath();

  if (pid) {
    try {
      if (process.platform === "win32") {
        cp.execSync(`taskkill /F /PID ${pid}`, { stdio: "ignore", windowsHide: true });
      } else {
        process.kill(pid, "SIGTERM");
      }
    } catch (_) {}
  }

  if (fs.existsSync(mainPy) && (pid || fs.existsSync(pidFile))) {
    const stopExec = (cachedRuntime && cachedRuntime.cliExec) || "python";
    try {
      cp.spawnSync(stopExec, [mainPy, "--stop", "--data-dir", dataDir], {
        cwd: appDir,
        stdio: "ignore",
        windowsHide: true,
        timeout: 2500,
        env: { ...process.env, TASK_OVERLAY_DATA_DIR: dataDir }
      });
    } catch (_) {}
  }

  if (fs.existsSync(pidFile)) {
    try {
      fs.unlinkSync(pidFile);
    } catch (_) {}
  }

  overlayChildProcess = null;
  updateStatusUI();

  if (!silent) {
    vscode.window.showInformationMessage("Antigravity Task Overlay dihentikan.");
  }
}

function restartOverlay(silent = false) {
  stopOverlay(true);
  setTimeout(() => {
    startOverlay(silent);
  }, 350);
}

function updateStatusUI() {
  const pid = getRunningOverlayPid();
  const running = Boolean(pid);

  if (statusBarItem) {
    statusBarItem.text = running ? "$(pulse) Task Overlay: Aktif" : "$(circle-slash) Task Overlay: Nonaktif";
    statusBarItem.tooltip = running
      ? `Antigravity Task Overlay sedang berjalan (PID: ${pid}). Klik untuk membuka panel konfigurasi.`
      : "Antigravity Task Overlay sedang berhenti. Klik untuk membuka panel konfigurasi.";
    statusBarItem.show();
  }

  if (sidebarProvider) {
    sidebarProvider.postStatusAndConfig();
  }
}

class TaskOverlaySidebarProvider {
  constructor(extensionUri) {
    this._extensionUri = extensionUri;
    this._view = null;
  }

  resolveWebviewView(webviewView) {
    this._view = webviewView;
    webviewView.webview.options = {
      enableScripts: true
    };

    webviewView.webview.html = this._getHtmlForWebview();

    webviewView.webview.onDidReceiveMessage((msg) => {
      switch (msg.type) {
        case "ready":
          this.postStatusAndConfig();
          break;
        case "start":
          startOverlay(false);
          break;
        case "stop":
          stopOverlay(false);
          break;
        case "restart":
          restartOverlay(false);
          break;
        case "updateConfig": {
          const patch = msg.payload || {};
          const prevCfg = readOverlayConfig();
          writeOverlayConfig(patch);

          if (
            typeof patch.auto_close_with_ide === "boolean" &&
            patch.auto_close_with_ide !== prevCfg.auto_close_with_ide &&
            getRunningOverlayPid()
          ) {
            restartOverlay(true);
          } else {
            this.postStatusAndConfig();
          }
          break;
        }
        case "snapPreset": {
          const preset = msg.preset || "top-right";
          writeOverlayConfig({ snap_preset: preset });
          setTimeout(() => {
            this.postStatusAndConfig();
          }, 500);
          break;
        }
        case "resetDefaults": {
          writeOverlayConfig({ ...DEFAULT_CONFIG, snap_preset: "top-right" });
          vscode.window.showInformationMessage("Konfigurasi Task Overlay dikembalikan ke pengaturan awal.");
          setTimeout(() => {
            this.postStatusAndConfig();
          }, 500);
          break;
        }
      }
    });
  }

  postStatusAndConfig() {
    if (!this._view) {
      return;
    }
    const pid = getRunningOverlayPid();
    const cfg = readOverlayConfig();
    this._view.webview.postMessage({
      type: "state",
      running: Boolean(pid),
      pid: pid || null,
      appDir: resolveAppDir(),
      config: cfg
    });
  }

  _getHtmlForWebview() {
    return `<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<style>
  :root {
    --bg-card: rgba(30, 41, 59, 0.55);
    --bg-card-hover: rgba(30, 41, 59, 0.8);
    --border-color: rgba(148, 163, 184, 0.18);
    --accent: #38bdf8;
    --accent-hover: #0ea5e9;
    --success: #10b981;
    --danger: #ef4444;
    --text-main: var(--vscode-foreground, #f1f5f9);
    --text-muted: var(--vscode-descriptionForeground, #94a3b8);
  }
  * {
    box-sizing: border-box;
  }
  body {
    padding: 12px;
    margin: 0;
    font-family: var(--vscode-font-family, "Segoe UI", sans-serif);
    font-size: 12px;
    color: var(--text-main);
    background: transparent;
    user-select: none;
  }
  .header-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 12px;
    margin-bottom: 12px;
  }
  .header-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
  }
  .app-title {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.2px;
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .status-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
  }
  .status-badge.running {
    background: rgba(16, 185, 129, 0.16);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.35);
  }
  .status-badge.stopped {
    background: rgba(239, 68, 68, 0.15);
    color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.3);
  }
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
  }
  .dot.running {
    background: #10b981;
    box-shadow: 0 0 6px #10b981;
  }
  .dot.stopped {
    background: #ef4444;
  }
  .btn-row {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 6px;
  }
  button {
    border: 1px solid var(--border-color);
    background: rgba(15, 23, 42, 0.65);
    color: var(--text-main);
    padding: 6px 8px;
    border-radius: 6px;
    font-size: 11.5px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
  }
  button:hover {
    background: rgba(56, 189, 248, 0.15);
    border-color: rgba(56, 189, 248, 0.45);
  }
  button.primary {
    background: rgba(16, 185, 129, 0.2);
    border-color: rgba(16, 185, 129, 0.45);
    color: #34d399;
  }
  button.primary:hover {
    background: rgba(16, 185, 129, 0.32);
  }
  button.danger {
    background: rgba(239, 68, 68, 0.16);
    border-color: rgba(239, 68, 68, 0.4);
    color: #f87171;
  }
  button.danger:hover {
    background: rgba(239, 68, 68, 0.28);
  }
  .section {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 11px 12px;
    margin-bottom: 10px;
  }
  .section-title {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: var(--accent);
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .control-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 0;
    border-bottom: 1px solid rgba(148, 163, 184, 0.08);
    gap: 8px;
  }
  .control-item:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }
  .control-label {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .control-label span.title {
    font-size: 12px;
    font-weight: 500;
  }
  .control-label span.desc {
    font-size: 10.5px;
    color: var(--text-muted);
  }
  /* Toggle Switch */
  .switch {
    position: relative;
    display: inline-block;
    width: 34px;
    height: 18px;
    flex-shrink: 0;
  }
  .switch input {
    opacity: 0;
    width: 0;
    height: 0;
  }
  .slider {
    position: absolute;
    cursor: pointer;
    top: 0; left: 0; right: 0; bottom: 0;
    background-color: rgba(100, 116, 139, 0.45);
    transition: .2s;
    border-radius: 18px;
  }
  .slider:before {
    position: absolute;
    content: "";
    height: 12px;
    width: 12px;
    left: 3px;
    bottom: 3px;
    background-color: #f8fafc;
    transition: .2s;
    border-radius: 50%;
  }
  input:checked + .slider {
    background-color: var(--accent);
  }
  input:checked + .slider:before {
    transform: translateX(16px);
  }
  /* Range & Number Inputs */
  .range-block {
    padding: 6px 0;
    border-bottom: 1px solid rgba(148, 163, 184, 0.08);
  }
  .range-block:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }
  .range-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 5px;
  }
  .range-val {
    font-family: monospace;
    font-size: 11px;
    color: var(--accent);
    background: rgba(56, 189, 248, 0.12);
    padding: 1px 6px;
    border-radius: 4px;
  }
  input[type="range"] {
    width: 100%;
    accent-color: var(--accent);
    cursor: pointer;
    height: 4px;
  }
  .coord-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-top: 6px;
  }
  .coord-box {
    display: flex;
    align-items: center;
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid var(--border-color);
    border-radius: 6px;
    padding: 4px 8px;
    justify-content: space-between;
  }
  .coord-box label {
    font-size: 11px;
    color: var(--text-muted);
    font-weight: 600;
  }
  .coord-box input[type="number"] {
    width: 65px;
    background: transparent;
    border: none;
    color: var(--text-main);
    font-family: monospace;
    font-size: 12px;
    text-align: right;
    outline: none;
  }
  .preset-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 5px;
    margin-top: 8px;
  }
  .preset-btn {
    font-size: 10.5px;
    padding: 5px 4px;
  }
  .footer-btn {
    width: 100%;
    margin-top: 4px;
    padding: 7px;
  }
</style>
</head>
<body>

  <!-- STATUS & PROCESS CONTROL -->
  <div class="header-card">
    <div class="header-top">
      <div class="app-title">
        <span>Task Overlay</span>
      </div>
      <div id="statusBadge" class="status-badge stopped">
        <span id="statusDot" class="dot stopped"></span>
        <span id="statusText">Berhenti</span>
      </div>
    </div>
    <div class="btn-row">
      <button id="btnStart" class="primary">Jalankan</button>
      <button id="btnStop" class="danger">Hentikan</button>
      <button id="btnRestart">Restart</button>
    </div>
  </div>

  <!-- 1. OTOMATISASI & JENDELA -->
  <div class="section">
    <div class="section-title">Otomatisasi & Jendela</div>

    <div class="control-item">
      <div class="control-label">
        <span class="title">Auto-Start saat IDE Dibuka</span>
        <span class="desc">Jalankan overlay otomatis ketika IDE aktif</span>
      </div>
      <label class="switch">
        <input type="checkbox" id="chkAutoStart" />
        <span class="slider"></span>
      </label>
    </div>

    <div class="control-item">
      <div class="control-label">
        <span class="title">Auto-Close saat IDE Ditutup</span>
        <span class="desc">Hentikan overlay otomatis ketika IDE ditutup</span>
      </div>
      <label class="switch">
        <input type="checkbox" id="chkAutoClose" />
        <span class="slider"></span>
      </label>
    </div>

    <div class="control-item">
      <div class="control-label">
        <span class="title">Always on Top (Pin Jendela)</span>
        <span class="desc">Tampilkan selalu di atas jendela aplikasi lain</span>
      </div>
      <label class="switch">
        <input type="checkbox" id="chkAlwaysOnTop" />
        <span class="slider"></span>
      </label>
    </div>

    <div class="range-block">
      <div class="range-header">
        <span>Opacity / Transparansi Jendela</span>
        <span id="valOpacity" class="range-val">100%</span>
      </div>
      <input type="range" id="rngOpacity" min="40" max="100" step="5" value="100" />
    </div>
  </div>

  <!-- 2. UKURAN & POSISI LAYAR -->
  <div class="section">
    <div class="section-title">Ukuran & Posisi Layar</div>

    <div class="range-block">
      <div class="range-header">
        <span>Panjang / Lebar Jendela</span>
        <span id="valWidth" class="range-val">390 px</span>
      </div>
      <input type="range" id="rngWidth" min="360" max="1200" step="10" value="390" />
    </div>

    <div class="range-block">
      <div class="range-header">
        <span>Tinggi Log Saat Expanded</span>
        <span id="valExpHeight" class="range-val">350 px</span>
      </div>
      <input type="range" id="rngExpHeight" min="250" max="820" step="10" value="350" />
    </div>

    <div class="range-block">
      <div class="range-header">
        <span>Koordinat Posisi Layar</span>
      </div>
      <div class="coord-grid">
        <div class="coord-box">
          <label>X</label>
          <input type="number" id="numPosX" step="10" value="1400" />
        </div>
        <div class="coord-box">
          <label>Y</label>
          <input type="number" id="numPosY" step="10" value="30" />
        </div>
      </div>

      <div class="preset-grid">
        <button class="preset-btn" data-preset="top-left">Kiri Atas</button>
        <button class="preset-btn" data-preset="top-center">Tengah Atas</button>
        <button class="preset-btn" data-preset="top-right">Kanan Atas</button>
        <button class="preset-btn" data-preset="bottom-left">Kiri Bawah</button>
        <button class="preset-btn" data-preset="bottom-right">Kanan Bawah</button>
      </div>
    </div>
  </div>

  <!-- 3. KOMPONEN UI & FITUR -->
  <div class="section">
    <div class="section-title">Komponen UI & Indikator</div>

    <div class="control-item">
      <div class="control-label">
        <span class="title">Lingkaran Kuota Token</span>
        <span class="desc">Indikator persentase kuota konteks di kiri atas</span>
      </div>
      <label class="switch">
        <input type="checkbox" id="chkQuotaRing" />
        <span class="slider"></span>
      </label>
    </div>

    <div class="control-item">
      <div class="control-label">
        <span class="title">Timer Durasi Eksekusi</span>
        <span class="desc">Penghitung waktu proses task berjalan</span>
      </div>
      <label class="switch">
        <input type="checkbox" id="chkDurationTimer" />
        <span class="slider"></span>
      </label>
    </div>

    <div class="control-item">
      <div class="control-label">
        <span class="title">Badge Model AI</span>
        <span class="desc">Animasi nama model saat task dimulai/berganti</span>
      </div>
      <label class="switch">
        <input type="checkbox" id="chkModelBadge" />
        <span class="slider"></span>
      </label>
    </div>

    <div class="control-item">
      <div class="control-label">
        <span class="title">Statistik Baris (+baris -baris)</span>
        <span class="desc">Tampilkan jumlah penambahan/penghapusan baris</span>
      </div>
      <label class="switch">
        <input type="checkbox" id="chkDiffStats" />
        <span class="slider"></span>
      </label>
    </div>

    <div class="control-item">
      <div class="control-label">
        <span class="title">Indikator Background Process</span>
        <span class="desc">Tampilkan daemon/command latar di Baris 3 atau 4</span>
      </div>
      <label class="switch">
        <input type="checkbox" id="chkBgProcess" />
        <span class="slider"></span>
      </label>
    </div>

    <div class="control-item">
      <div class="control-label">
        <span class="title">Ringkasan Penyelesaian Otomatis</span>
        <span class="desc">Tampilkan ringkasan singkat setelah tugas selesai</span>
      </div>
      <label class="switch">
        <input type="checkbox" id="chkCompletionSummary" />
        <span class="slider"></span>
      </label>
    </div>
  </div>

  <!-- 4. DURASI ANIMASI & PERFORMA -->
  <div class="section">
    <div class="section-title">Durasi Animasi & Performa</div>

    <div class="range-block">
      <div class="range-header">
        <span>Kecepatan Auto-Scroll Teks</span>
        <span id="valMarquee" class="range-val">2 px/tick</span>
      </div>
      <input type="range" id="rngMarquee" min="1" max="6" step="1" value="2" />
    </div>

    <div class="range-block">
      <div class="range-header">
        <span>Durasi Tampil Badge Model</span>
        <span id="valBadgeDur" class="range-val">4.5 dtk</span>
      </div>
      <input type="range" id="rngBadgeDur" min="1500" max="12000" step="500" value="4500" />
    </div>

    <div class="range-block">
      <div class="range-header">
        <span>Durasi Tampil Ringkasan Selesai</span>
        <span id="valSummaryDur" class="range-val">6.5 dtk</span>
      </div>
      <input type="range" id="rngSummaryDur" min="2500" max="15000" step="500" value="6500" />
    </div>

    <div class="range-block">
      <div class="range-header">
        <span>Durasi Sekilas Command & Response</span>
        <span id="valGlanceDur" class="range-val">6.0 dtk</span>
      </div>
      <input type="range" id="rngGlanceDur" min="2500" max="15000" step="500" value="6000" />
    </div>

    <div class="range-block">
      <div class="range-header">
        <span>Interval Polling Realtime</span>
        <span id="valPoll" class="range-val">320 ms</span>
      </div>
      <input type="range" id="rngPoll" min="150" max="1000" step="30" value="320" />
    </div>
  </div>

  <button id="btnResetDefaults" class="footer-btn">Reset ke Pengaturan Awal (Default)</button>

<script>
  const vscode = acquireVsCodeApi();

  const el = (id) => document.getElementById(id);

  function sendConfigPatch(patch) {
    vscode.postMessage({ type: "updateConfig", payload: patch });
  }

  // Buttons
  el("btnStart").addEventListener("click", () => vscode.postMessage({ type: "start" }));
  el("btnStop").addEventListener("click", () => vscode.postMessage({ type: "stop" }));
  el("btnRestart").addEventListener("click", () => vscode.postMessage({ type: "restart" }));
  el("btnResetDefaults").addEventListener("click", () => vscode.postMessage({ type: "resetDefaults" }));

  document.querySelectorAll(".preset-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      vscode.postMessage({ type: "snapPreset", preset: btn.getAttribute("data-preset") });
    });
  });

  // Checkboxes
  const checkboxMap = [
    ["chkAutoStart", "auto_start"],
    ["chkAutoClose", "auto_close_with_ide"],
    ["chkAlwaysOnTop", "always_on_top"],
    ["chkQuotaRing", "show_quota_ring"],
    ["chkDurationTimer", "show_duration_timer"],
    ["chkModelBadge", "show_model_badge"],
    ["chkDiffStats", "show_diff_stats"],
    ["chkBgProcess", "show_bg_process"],
    ["chkCompletionSummary", "show_completion_summary"]
  ];

  checkboxMap.forEach(([id, key]) => {
    el(id).addEventListener("change", (e) => {
      sendConfigPatch({ [key]: e.target.checked });
    });
  });

  // Sliders
  function bindSlider(id, valId, key, formatter) {
    const input = el(id);
    const valSpan = el(valId);
    input.addEventListener("input", () => {
      valSpan.textContent = formatter(Number(input.value));
    });
    input.addEventListener("change", () => {
      sendConfigPatch({ [key]: Number(input.value) });
    });
  }

  bindSlider("rngOpacity", "valOpacity", "window_opacity", (v) => v + "%");
  bindSlider("rngWidth", "valWidth", "width", (v) => v + " px");
  bindSlider("rngExpHeight", "valExpHeight", "expanded_height", (v) => v + " px");
  bindSlider("rngMarquee", "valMarquee", "marquee_speed", (v) => v + " px/tick");
  bindSlider("rngBadgeDur", "valBadgeDur", "model_badge_duration_ms", (v) => (v / 1000).toFixed(1) + " dtk");
  bindSlider("rngSummaryDur", "valSummaryDur", "summary_duration_ms", (v) => (v / 1000).toFixed(1) + " dtk");
  bindSlider("rngGlanceDur", "valGlanceDur", "cmd_glance_duration_ms", (v) => (v / 1000).toFixed(1) + " dtk");
  bindSlider("rngPoll", "valPoll", "poll_interval_active_ms", (v) => v + " ms");

  // X/Y Coordinate Inputs
  ["numPosX", "numPosY"].forEach((id) => {
    el(id).addEventListener("change", () => {
      const x = parseInt(el("numPosX").value, 10);
      const y = parseInt(el("numPosY").value, 10);
      if (!isNaN(x) && !isNaN(y)) {
        sendConfigPatch({ x, y });
      }
    });
  });

  window.addEventListener("message", (event) => {
    const msg = event.data;
    if (msg.type === "state") {
      const badge = el("statusBadge");
      const dot = el("statusDot");
      const txt = el("statusText");
      if (msg.running) {
        badge.className = "status-badge running";
        dot.className = "dot running";
        txt.textContent = "Aktif (PID " + msg.pid + ")";
      } else {
        badge.className = "status-badge stopped";
        dot.className = "dot stopped";
        txt.textContent = "Berhenti";
      }

      const c = msg.config || {};
      el("chkAutoStart").checked = c.auto_start !== false;
      el("chkAutoClose").checked = c.auto_close_with_ide !== false;
      el("chkAlwaysOnTop").checked = c.always_on_top !== false;
      el("chkQuotaRing").checked = c.show_quota_ring !== false;
      el("chkDurationTimer").checked = c.show_duration_timer !== false;
      el("chkModelBadge").checked = c.show_model_badge !== false;
      el("chkDiffStats").checked = c.show_diff_stats !== false;
      el("chkBgProcess").checked = c.show_bg_process !== false;
      el("chkCompletionSummary").checked = c.show_completion_summary !== false;

      if (typeof c.window_opacity === "number") {
        el("rngOpacity").value = c.window_opacity;
        el("valOpacity").textContent = c.window_opacity + "%";
      }
      if (typeof c.width === "number") {
        el("rngWidth").value = c.width;
        el("valWidth").textContent = c.width + " px";
      }
      if (typeof c.expanded_height === "number") {
        el("rngExpHeight").value = c.expanded_height;
        el("valExpHeight").textContent = c.expanded_height + " px";
      }
      if (typeof c.x === "number" && document.activeElement !== el("numPosX")) {
        el("numPosX").value = c.x;
      }
      if (typeof c.y === "number" && document.activeElement !== el("numPosY")) {
        el("numPosY").value = c.y;
      }
      if (typeof c.marquee_speed === "number") {
        el("rngMarquee").value = c.marquee_speed;
        el("valMarquee").textContent = c.marquee_speed + " px/tick";
      }
      if (typeof c.model_badge_duration_ms === "number") {
        el("rngBadgeDur").value = c.model_badge_duration_ms;
        el("valBadgeDur").textContent = (c.model_badge_duration_ms / 1000).toFixed(1) + " dtk";
      }
      if (typeof c.summary_duration_ms === "number") {
        el("rngSummaryDur").value = c.summary_duration_ms;
        el("valSummaryDur").textContent = (c.summary_duration_ms / 1000).toFixed(1) + " dtk";
      }
      if (typeof c.cmd_glance_duration_ms === "number") {
        el("rngGlanceDur").value = c.cmd_glance_duration_ms;
        el("valGlanceDur").textContent = (c.cmd_glance_duration_ms / 1000).toFixed(1) + " dtk";
      }
      if (typeof c.poll_interval_active_ms === "number") {
        el("rngPoll").value = c.poll_interval_active_ms;
        el("valPoll").textContent = c.poll_interval_active_ms + " ms";
      }
    }
  });

  vscode.postMessage({ type: "ready" });
</script>
</body>
</html>`;
  }
}

function activate(context) {
  sidebarProvider = new TaskOverlaySidebarProvider(context.extensionUri);

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      "antigravityTaskOverlay.controlPanel",
      sidebarProvider,
      { webviewOptions: { retainContextWhenHidden: true } }
    )
  );

  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.command = "antigravityTaskOverlay.openPanel";
  context.subscriptions.push(statusBarItem);

  context.subscriptions.push(
    vscode.commands.registerCommand("antigravityTaskOverlay.start", () => startOverlay(false)),
    vscode.commands.registerCommand("antigravityTaskOverlay.stop", () => stopOverlay(false)),
    vscode.commands.registerCommand("antigravityTaskOverlay.restart", () => restartOverlay(false)),
    vscode.commands.registerCommand("antigravityTaskOverlay.resetPosition", () => {
      writeOverlayConfig({ snap_preset: "top-right" });
      vscode.window.showInformationMessage("Posisi Task Overlay direset ke Kanan Atas.");
    }),
    vscode.commands.registerCommand("antigravityTaskOverlay.openPanel", async () => {
      await vscode.commands.executeCommand("workbench.view.extension.antigravity-task-overlay");
    })
  );

  // Auto-Start saat IDE terbuka jika diaktifkan di konfigurasi
  const cfg = readOverlayConfig();
  const vsAutoStart = vscode.workspace.getConfiguration("antigravityTaskOverlay").get("autoStart", true);
  if (cfg.auto_start !== false && vsAutoStart !== false) {
    startOverlay(true);
  } else {
    updateStatusUI();
  }

  // Pantau status proses & sinkronisasi perubahan posisi/ukuran dari jendela desktop secara periodik
  statusPollTimer = setInterval(() => {
    updateStatusUI();
  }, 1500);

  context.subscriptions.push({
    dispose: () => {
      if (statusPollTimer) {
        clearInterval(statusPollTimer);
        statusPollTimer = null;
      }
    }
  });
}

function deactivate() {
  if (statusPollTimer) {
    clearInterval(statusPollTimer);
    statusPollTimer = null;
  }
  const cfg = readOverlayConfig();
  const vsAutoClose = vscode.workspace.getConfiguration("antigravityTaskOverlay").get("autoCloseWithIde", true);
  if (cfg.auto_close_with_ide !== false && vsAutoClose !== false) {
    stopOverlay(true);
  }
}

module.exports = {
  activate,
  deactivate
};

