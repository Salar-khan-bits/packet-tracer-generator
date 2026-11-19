/* ============================================================================
 * ptbot bridge -- minimal Packet Tracer <-> Python file-drop bridge
 * ----------------------------------------------------------------------------
 * Paste this ENTIRE file into Packet Tracer's Script Module editor:
 *   Extensions -> Scripting -> Configure PT Script Modules... -> Add
 *   General tab:  ID = com.ptbot.bridge   Name = ptbot   Startup = On Startup
 *   Script Engine tab: Add a file named bridge.js -> paste this -> Apply
 *   Security Privileges tab: tick Application, File Operations,
 *       Get Network Info, (optional) Miscellaneous UI
 *   Save -> select the module -> Start, then quit PT once with File -> Exit.
 *
 * ES5 / QtScript ONLY: var and function. No let/const, arrow fns, templates.
 *
 * How it works (a "mailbox" on disk -- no network sockets at all):
 *   Python writes  <HOME>/ptbot/jobs/<id>.json   = {"id","op","args"}
 *   This bridge (watching jobs/) runs the op via PT's ipc API and writes
 *                  <HOME>/ptbot/results/<id>.json = {"id","ok","result"|"error"}
 *   then deletes the job file.
 *
 * The ipc API surface used here (getUserFolder, systemFileManager, network,
 * getDevice, getFileWatcher, ...) is PT's own documented Scripting/Extensions
 * API. Mailbox pattern and several call names were learned from the MIT-licensed
 * packet-tracer-mcp project (c) 2026 Pawel Sampir; this file is an original,
 * minimal reimplementation for a read-only spike.
 * ========================================================================== */

var PTBOT_HOME = String(ipc.appWindow().getUserFolder()) + "/ptbot";
var PTBOT_JOBS = PTBOT_HOME + "/jobs";
var PTBOT_RESULTS = PTBOT_HOME + "/results";

var PTBOT_BUSY = false;
var PTBOT_INITED = false;
var PTBOT_SEEN = {};

if (typeof PTBOT_EVALS === "undefined") { PTBOT_EVALS = 0; }
PTBOT_EVALS = PTBOT_EVALS + 1;

/* Device type ids (PT 9.0.1) we care about for naming. */
var TYPE_NAMES = {
    0: "Router", 1: "Switch", 4: "Hub", 8: "PC", 9: "Server",
    16: "MultiLayerSwitch", 17: "Laptop", 18: "TabletPC"
};

function ptLog(msg) {
    try { ipc.appWindow().writeToPT("[ptbot] " + msg + "\n"); } catch (e) {}
}

function baseName(p) {
    var s = String(p);
    var a = s.lastIndexOf("/"), b = s.lastIndexOf("\\");
    var i = a > b ? a : b;
    return i >= 0 ? s.substring(i + 1) : s;
}

function safeId(id) {
    return String(id == null ? "" : id).replace(/[^A-Za-z0-9_.-]/g, "_");
}

function safeStringify(v) {
    try {
        var s = JSON.stringify(v);
        return typeof s === "undefined" ? String(v) : s;
    } catch (e) { return String(v); }
}

function errMsg(e) {
    if (!e) { return "unknown error"; }
    return e.message ? String(e.message) : String(e);
}

function ensureDir(path) {
    try {
        var fm = ipc.systemFileManager();
        if (!fm.directoryExists(path)) { fm.makeDirectory(path); }
    } catch (e) { ptLog("ensureDir(" + path + ") failed: " + errMsg(e)); }
}

function ensureDirs() {
    ensureDir(PTBOT_HOME);
    ensureDir(PTBOT_JOBS);
    ensureDir(PTBOT_RESULTS);
}

function listJobFiles() {
    var out = [];
    try {
        var fm = ipc.systemFileManager();
        var files = fm.getFilesInDirectory(PTBOT_JOBS);
        if (!files) { return out; }
        var n = files.length;
        if (typeof n === "undefined") { return out; }
        var i, name;
        for (i = 0; i < n; i++) {
            name = baseName(files[i]);
            if (/\.json$/i.test(name) && !/\.tmp$/i.test(name)) { out.push(name); }
        }
    } catch (e) { ptLog("listJobFiles failed: " + errMsg(e)); }
    return out;
}

function writeResult(id, ok, payload) {
    var obj = { id: String(id), ok: !!ok };
    if (ok) { obj.result = payload; } else { obj.error = String(payload); }
    var path = PTBOT_RESULTS + "/" + safeId(id) + ".json";
    try {
        var fm = ipc.systemFileManager();
        if (!fm.writePlainTextToFile(path, safeStringify(obj))) {
            fm.writeTextToFile(path, safeStringify(obj));
        }
    } catch (e) { ptLog("writeResult(" + id + ") failed: " + errMsg(e)); }
}

function removeJob(fileName) {
    try { ipc.systemFileManager().removeFile(PTBOT_JOBS + "/" + fileName); }
    catch (e) { ptLog("removeJob failed: " + errMsg(e)); }
}

/* ---- operations ---------------------------------------------------------- */
function dispatch(op, args) {
    args = args || {};

    if (op === "ping") {
        return {
            version: String(ipc.appWindow().getVersion()),
            deviceCount: ipc.network().getDeviceCount()
        };
    }

    if (op === "list_devices") {
        var net = ipc.network();
        var count = net.getDeviceCount();
        var devices = [];
        var i, d, t;
        for (i = 0; i < count; i++) {
            d = net.getDeviceAt(i);
            if (!d) { continue; }
            t = null;
            try { t = d.getType(); } catch (e) { t = null; }
            devices.push({
                name: String(d.getName()),
                type: t,
                typeName: (t !== null && TYPE_NAMES.hasOwnProperty(t)) ? TYPE_NAMES[t] : null,
                model: String(d.getModel())
            });
        }
        var links = 0;
        try { links = net.getLinkCount(); } catch (e) { links = 0; }
        return { devices: devices, links: links };
    }

    throw new Error("unknown op: " + op);
}

function processJob(fileName) {
    var id = fileName.replace(/\.json$/i, "");
    if (PTBOT_SEEN.hasOwnProperty(id)) { return; }
    PTBOT_SEEN[id] = true;

    var text = "";
    try {
        text = ipc.systemFileManager().getFileContents(PTBOT_JOBS + "/" + fileName);
    } catch (e) {
        writeResult(id, false, "cannot read job: " + errMsg(e));
        removeJob(fileName); return;
    }
    var req = null;
    try { req = JSON.parse(text); }
    catch (e) {
        writeResult(id, false, "invalid job JSON: " + errMsg(e));
        removeJob(fileName); return;
    }
    var op = req && req.op ? String(req.op) : "";
    var args = (req && req.args) ? req.args : {};
    var jobId = (req && req.id) ? req.id : id;
    try {
        writeResult(jobId, true, dispatch(op, args));
        ptLog("ok: " + op + " (" + jobId + ")");
    } catch (e) {
        writeResult(jobId, false, errMsg(e));
        ptLog("error: " + op + " (" + jobId + "): " + errMsg(e));
    } finally {
        removeJob(fileName);
    }
}

function processPending() {
    if (PTBOT_BUSY) { return; }
    PTBOT_BUSY = true;
    try {
        var files = listJobFiles();
        var i;
        for (i = 0; i < files.length; i++) { processJob(files[i]); }
    } catch (e) { ptLog("processPending failed: " + errMsg(e)); }
    finally { PTBOT_BUSY = false; }
}

var ptbot_rescan = processPending;

function onFsEvent(src, args) { processPending(); }

function setupWatcher() {
    try {
        var w = ipc.systemFileManager().getFileWatcher();
        w.registerEvent("fileChanged", null, onFsEvent);
        w.registerEvent("directoryChanged", null, onFsEvent);
        w.addPath(PTBOT_JOBS);
        ptLog("watching " + PTBOT_JOBS);
    } catch (e) {
        ptLog("watcher setup failed (use Run File to rescan): " + errMsg(e));
    }
}

function main() {
    ensureDirs();
    if (!PTBOT_INITED) { setupWatcher(); PTBOT_INITED = true; }
    ptLog("bridge ready (home=" + PTBOT_HOME + ")");
    processPending();
}

/* "Run File" re-evaluates without calling main(); auto-run so it forces a rescan. */
if (PTBOT_EVALS > 1) {
    try { main(); } catch (e) { ptLog("rescan-on-run failed: " + errMsg(e)); }
}
