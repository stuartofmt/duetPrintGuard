#!/usr/bin/env python3
"""DWC tools - one small web app for DuetWebControl plugin development.
  /              Home          choose a tool
  /createplugin  Create a Plugin  build / zip a DWC plugin
  /dwcversion    Create DWC Version    clone a DWC version, npm install, run its dev server
  /settings      Settings      the folders holding the DWC versions and the plugins
  /readme        Instructions on use

The two tools have separate jobs, so a DWC dev server can keep running while you build plugins.

Setup (Linux, e.g. Raspberry Pi OS):  sudo apt install python3-flask git nodejs npm
Setup (Windows 10 or later):          install Python 3.8+, Git for Windows and Node.js, then: pip install flask
Run:     python3 plugin_tools.py       (Windows: python plugin_tools.py)
The operating system (Linux or Windows) is detected at start-up; no zip program is needed on either.
Open:    the address printed at start-up: this computer's network address, on the preferred port
         from the Settings page, or else the first free port from 17800.
         The first time (no settings file yet) the browser opens at /readme instead of Home.

Folder layout (both folders can be changed on the Settings page; until then they are the folder this script is in):
  <DWC versions folder>/<dwc version>/                  <- DWCVersion clones into here
  <Plugins folder>/<plugin name>/plugin<plugin version>/Code/plugin.json
Result of CreatePlugin:
  <Plugins folder>/<plugin name>/plugin<plugin version>/<plugin version>-<plugin name>-<manifest version>.zip

The folders, the preferred port, the remembered CreatePlugin exclusions and the last selections made in
each tool (they become the defaults next time) are stored together in .plugin_build_exclusions.json,
in the same folder as this script.
"""
import json
import logging
import os
import platform
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
import zipfile
from glob import glob

from flask import Flask, jsonify, request

PLATFORM = platform.system()          # "Linux", "Windows", ...
IS_WINDOWS = PLATFORM == "Windows"    # everything else is handled like Linux
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))   # where this script is installed
# Until they are set on the Settings page, both folders are the folder this script is installed in
DEFAULT_DWC_VERSIONS = SCRIPT_DIR
DEFAULT_PLUGINS = SCRIPT_DIR
DEFAULTS = {"dwc_versions_dir": DEFAULT_DWC_VERSIONS, "plugins_dir": DEFAULT_PLUGINS}
DEFAULT_CODE_PATH = "Code"   # where a plugin's files live, relative to its plugin<version> folder
# The address this tool listens on is worked out at start-up by validate_port() (see main())
HOST = "127.0.0.1"
PORT = 0
# Settings file: the two folders above, the preferred port, the ticked exclusion files remembered per
# DWC version / plugin / plugin version, and the last selections made in each tool. It lives next to this
# script. No other location is ever looked at, and no environment variable changes it.
SETTINGS_NAME = ".plugin_build_exclusions.json"
SETTINGS_FILE = os.path.join(SCRIPT_DIR, SETTINGS_NAME)
# Always left out of a zip-only build (files ticked in the UI are left out as well)
ALWAYS_SKIP_DIRS = ("__pycache__", "venv")
ALWAYS_SKIP_SUFFIXES = (".log", ".pyc")
REPO = "https://github.com/Duet3D/DuetWebControl"
GIT_ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0")  # never hang waiting for a git password

app = Flask(__name__)
logger = logging.getLogger("plugin_tools")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# Both dev servers print their address: Vite "  ➜  Local:   http://localhost:3000/" (DWC 3.7+) and
# Vue CLI "  - Local:   http://localhost:8080/" (older DWC)
LOCAL_URL = re.compile(r"Local:\s+(https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::\d+)?\S*)")
READY_TIMEOUT = 30   # seconds to wait for that URL to answer HTTP 200
READY = "ready"      # returned by Job.serve() when the dev server is up and left running


def http_status(url):
    """HTTP status of url using curl (0 = no connection, None = could not tell)."""
    try:
        r = subprocess.run(["curl", "-s", "-o", os.devnull, "-w", "%{http_code}", "--max-time", "5", url],
                           capture_output=True, text=True, timeout=10)
        return int(r.stdout.strip() or 0)
    except FileNotFoundError:  # curl not installed: do the same check in Python
        try:
            return urllib.request.urlopen(url, timeout=5).status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            return 0
    except (ValueError, subprocess.TimeoutExpired):
        return None


def force_quit(code=1):
    """Stop the app straight away (used when start-up cannot continue)."""
    logger.critical("Exiting")
    sys.exit(code)


def port_in_use(ip_address, port):
    #  A successful connection means something is already listening there
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((ip_address, port)) == 0


def validate_port(port=0, start_port=17800, max_tries=100):
    #  Get the local ip address
    this_ip_address = ''
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))  # doesn't even have to be reachable
        this_ip_address = s.getsockname()[0]
    except Exception as e:
        logger.critical(f'''Unknown error trying to get the local IP address''')
        logger.critical(f'''{e}''')
        force_quit(1)
    finally:
        s.close()

    if port:
        #  A port was provided - check that it is available
        if port_in_use(this_ip_address, port):
            logger.warning(f'''Port {port} is already in use - falling back to searching from {start_port}''')
            port = 0
    else:
        logger.info(f'''No port number was provided - searching for a free port starting at {start_port}''')

    if not port:
        #  No usable port yet - search for one starting at start_port
        for candidate in range(start_port, start_port + max_tries):
            if not port_in_use(this_ip_address, candidate):
                port = candidate
                break
        else:
            logger.critical(f'''No free port found between {start_port} and {start_port + max_tries - 1}''')
            force_quit(1)

    logger.info(f'''IP address {this_ip_address} with port {port} is available''')
    return this_ip_address, port


# ---------- running and stopping programs (Linux and Windows) ----------
def popen(cmd, cwd=None, env=None):
    """Start cmd with its output piped back. It gets its own process group (Linux: session) so that
    Stop can end it together with everything it starts (npm -> node -> the dev server ...)."""
    exe = shutil.which(cmd[0])   # on Windows this finds npm.cmd, which Popen cannot find by the bare name
    full = [exe or cmd[0]] + list(cmd[1:])
    extra = {}
    if IS_WINDOWS:
        extra["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    else:
        extra["start_new_session"] = True
    return subprocess.Popen(
        full, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",   # npm prints UTF-8 whatever the Windows code page is
        bufsize=1, **extra)


def kill_tree(proc, force_after=None):
    """End proc and everything it started. With force_after (seconds), make sure it is really gone."""
    if IS_WINDOWS:
        # taskkill /T ends the whole tree. /F is needed: console programs ignore a polite close request.
        try:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=15)
        except (OSError, subprocess.SubprocessError):
            try:
                proc.kill()
            except OSError:
                pass
        if force_after:
            try:
                proc.wait(timeout=force_after)
            except subprocess.TimeoutExpired:
                pass
        return
    pgid = proc.pid  # start_new_session=True makes the group id equal the pid
    try:
        os.killpg(pgid, signal.SIGTERM)
        if force_after:
            for _ in range(int(force_after * 10)):
                try:
                    os.killpg(pgid, 0)
                except ProcessLookupError:
                    return
                time.sleep(0.1)
            os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def rmtree_force(path, ignore_errors=False):
    """Delete a folder tree. Windows refuses to delete read-only files (git makes plenty), so those are
    made writable first, and the long-path prefix is used because node_modules gets very deep."""
    if IS_WINDOWS:
        path = os.path.abspath(path)
        path = "\\\\?\\UNC\\" + path[2:] if path.startswith("\\\\") else "\\\\?\\" + path

    def retry(func, failed_path, *_):
        os.chmod(failed_path, stat.S_IWRITE)
        func(failed_path)

    handler = {"onexc": retry} if sys.version_info >= (3, 12) else {"onerror": retry}
    try:
        shutil.rmtree(path, **handler)
    except OSError:
        if not ignore_errors:
            raise


# ---------- background jobs ----------
class Job:
    """One background job (a run of commands) whose output the page polls.
    Each tool has its own Job, so they can run at the same time."""

    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.run = 0
        self.lines = []
        self.stopping = False
        self.busy = False
        self.service = None       # a server left running in the background after the job finished
        self.service_url = ""

    def begin(self):
        """Claim the job. Returns a fresh list for the output, or None if already running."""
        with self.lock:
            if self.busy:
                return None
            self.lines = []
            self.proc = None
            self.run += 1
            self.stopping = False
            self.busy = True
            return self.lines

    def step(self, lines, cmd, cwd, title=None, env=None):
        """Run one command, streaming its output. Returns the exit code, or None if stopped."""
        if title:
            lines.append(f"=== {title} ===")
        lines.append("$ " + " ".join(cmd))
        with self.lock:
            if self.stopping:
                return None
            try:
                proc = popen(cmd, cwd, env)
            except OSError as e:
                lines.append(f"Could not start {cmd[0]}: {e}")
                return 127
            self.proc = proc
        for line in proc.stdout:
            lines.append(ANSI.sub("", line.rstrip("\n")))
        return proc.wait()

    def serve(self, lines, cmd, cwd, title=None, env=None):
        """Run a long-lived dev server. As soon as it prints its Local URL and curl gets HTTP 200
        from it, return READY and leave it running in the background (its output keeps flowing
        into the log). Otherwise wait for it to exit and return the exit code, like step()."""
        if title:
            lines.append(f"=== {title} ===")
        lines.append("$ " + " ".join(cmd))
        with self.lock:
            if self.stopping:
                return None
            try:
                proc = popen(cmd, cwd, env)
            except OSError as e:
                lines.append(f"Could not start {cmd[0]}: {e}")
                return 127
            self.proc = proc
        for line in proc.stdout:
            text = ANSI.sub("", line.rstrip("\n"))
            lines.append(text)
            m = LOCAL_URL.search(text)
            if m and self._answers_200(lines, proc, m.group(1)):
                self.service, self.service_url = proc, m.group(1)
                threading.Thread(target=self._drain, args=(lines, proc), daemon=True).start()
                return READY
        return proc.wait()

    def _answers_200(self, lines, proc, url):
        lines.append(f"Checking {url} with curl ...")
        status = None
        for _ in range(READY_TIMEOUT):
            if self.stopping or proc.poll() is not None:
                return False
            status = http_status(url)
            if status == 200:
                lines.append("curl: HTTP 200 - dev server is up, so the job is done "
                             "(the server keeps running; the job does not wait for any further bundling)")
                return True
            time.sleep(1)
        lines.append(f"curl did not get HTTP 200 (last status: {status}) - still waiting for the dev server")
        return False

    def _drain(self, lines, proc):
        """After the job has finished: keep copying the dev server's output into the log."""
        for line in proc.stdout:
            lines.append(ANSI.sub("", line.rstrip("\n")))
        code = proc.wait()
        lines.append("--- dev server stopped ---" if self.stopping else f"--- dev server exited (code {code}) ---")
        if self.service is proc:
            self.service, self.service_url = None, ""

    def service_running(self):
        p = self.service
        return p is not None and p.poll() is None

    def terminate(self, force_after=None):
        """Stop the current command and everything it started (npm, node, ...)."""
        with self.lock:
            self.stopping = True
            p = self.proc
        if p is None or p.poll() is not None:
            return
        kill_tree(p, force_after)

    def view(self, n, run):
        if run != self.run:
            n = 0  # a new run started: send its output from the top
        lines = self.lines
        return {"run": self.run, "total": len(lines), "lines": lines[n:], "running": self.busy,
                "service": self.service_url if self.service_running() else ""}


plugin_job = Job()   # CreatePlugin
dwc_job = Job()      # DWCVersion
JOBS = (plugin_job, dwc_job)


# ---------- settings file: folders + remembered exclusions ----------
save_lock = threading.Lock()


def load_store():
    """Settings file layout: {"format": 2, "config": {...}, "last": {tool: {...}},
    "exclusions": {dwc: {plugin: {pver: [files]}}}}. A missing or unrecognised file counts as empty."""
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict) or data.get("format") != 2:
        data = {"format": 2}
    if not isinstance(data.get("config"), dict):
        data["config"] = {}
    if not isinstance(data.get("exclusions"), dict):
        data["exclusions"] = {}
    if not isinstance(data.get("last"), dict):
        data["last"] = {}
    return data


def write_store(data):
    """Write the settings file (call with save_lock held). Returns an error message, or None."""
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE) or ".", exist_ok=True)
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, SETTINGS_FILE)  # atomic, so a crash can't leave half a file
    except OSError as e:
        return str(e)
    return None


def folder_setting(key, default):
    v = load_store()["config"].get(key)
    return v if isinstance(v, str) and v.strip() else default


def dwc_versions_dir():
    return folder_setting("dwc_versions_dir", DEFAULT_DWC_VERSIONS)


def plugins_dir():
    return folder_setting("plugins_dir", DEFAULT_PLUGINS)


def code_path():
    """Folder holding plugin.json and the plugin's files, relative to the plugin<version> folder."""
    v = load_store()["config"].get("code_path")
    return v if isinstance(v, str) and v.strip() else DEFAULT_CODE_PATH


def code_dir_for(plugin, pver):
    return os.path.normpath(os.path.join(plugins_dir(), plugin, "plugin" + pver, code_path()))


def preferred_port():
    """Port this tool's web page should use (0 = no preference: the first free port from 17800).
    Only read at start-up."""
    v = load_store()["config"].get("preferred_port", 0)
    ok = isinstance(v, int) and not isinstance(v, bool) and (v == 0 or 1024 <= v <= 65535)
    return v if ok else 0


def saved_excludes(dwc, plugin, pver):
    """Files ticked the last time this DWC version / plugin / plugin version was run."""
    try:
        files = load_store()["exclusions"][dwc][plugin][pver]
    except (KeyError, TypeError):
        return []
    return [x for x in files if isinstance(x, str)] if isinstance(files, list) else []


def saved_last(tool):
    """The selections made the last time this tool was run (empty if never)."""
    v = load_store()["last"].get(tool)
    return v if isinstance(v, dict) else {}


def save_last(tool, values):
    """Remember a tool's selections as the next defaults. Returns an error message, or None."""
    with save_lock:
        data = load_store()
        data["last"][tool] = values
        return write_store(data)


def remember_plugin_run(dwc, plugin, pver, files):
    """CreatePlugin: remember the exclusions for this combination and the selections themselves.
    Returns an error message, or None."""
    with save_lock:
        data = load_store()
        node = data["exclusions"]
        for key in (dwc, plugin):
            if not isinstance(node.get(key), dict):
                node[key] = {}
            node = node[key]
        if files:
            node[pver] = files
        else:
            node.pop(pver, None)
        data["last"]["createplugin"] = {"dwc": dwc, "plugin": plugin, "plugin_version": pver}
        return write_store(data)


# ---------- folder listings ----------
def natural(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def subdirs(path):
    """Sub-folder names of path, naturally sorted (3.6 before 3.10)."""
    try:
        names = [d for d in os.listdir(path)
                 if os.path.isdir(os.path.join(path, d)) and not d.startswith(".")]
    except OSError:
        return []
    return sorted(names, key=natural)


VERSION_NAME = re.compile(r"[0-9][0-9A-Za-z._-]*")  # 3.5.1, 3.6-dev ... (git tag is "v" + this)


def dwc_versions():
    """DWC version folders: sub-folders of the DWC versions folder whose name looks like a version."""
    return [d for d in subdirs(dwc_versions_dir()) if VERSION_NAME.fullmatch(d)]


def plugin_versions(name):
    """Folders called plugin<version>; returned without the 'plugin' prefix."""
    return [d[6:] for d in subdirs(os.path.join(plugins_dir(), name))
            if d.startswith("plugin") and len(d) > 6]


def code_files(plugin, pver, limit=3000):
    """Files under the plugin's Code folder (paths relative to it) that could be excluded.
    Things the default exclusions already remove are left out of the list."""
    code_dir = code_dir_for(plugin, pver)
    out = []
    for dirpath, dirnames, filenames in os.walk(code_dir):
        dirnames[:] = [d for d in dirnames if d not in ALWAYS_SKIP_DIRS]
        for f in filenames:
            if f.endswith(ALWAYS_SKIP_SUFFIXES):
                continue
            out.append(os.path.relpath(os.path.join(dirpath, f), code_dir).replace(os.sep, "/"))
            if len(out) >= limit:
                return sorted(out, key=str.lower)
    return sorted(out, key=str.lower)


def zip_folder(job, lines, out_zip, code_dir, exclude):
    """Zip the contents of code_dir into out_zip (paths inside the zip start at code_dir), leaving out
    __pycache__ and venv folders, *.log and *.pyc files, and the files in `exclude`.
    Done with Python's zipfile so that no zip program is needed (Windows has none).
    Returns the number of files added, or None if the job was stopped. A partial or empty zip is never left behind."""
    skip = set(exclude)
    count = 0
    try:
        # strict_timestamps=False: files dated before 1980 are accepted instead of raising an error
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as z:
            for dirpath, dirnames, filenames in os.walk(code_dir):
                dirnames[:] = sorted(d for d in dirnames if d not in ALWAYS_SKIP_DIRS)
                rel_dir = os.path.relpath(dirpath, code_dir).replace(os.sep, "/")
                if rel_dir != ".":
                    z.write(dirpath, rel_dir + "/")   # a folder entry, as zip -r makes
                for name in sorted(filenames):
                    rel = name if rel_dir == "." else f"{rel_dir}/{name}"
                    if name.endswith(ALWAYS_SKIP_SUFFIXES) or rel in skip:
                        continue
                    if job.stopping:
                        raise InterruptedError
                    z.write(os.path.join(dirpath, name), rel)
                    lines.append(f"  adding: {rel}")
                    count += 1
    except InterruptedError:
        count = None
    except BaseException:
        if os.path.exists(out_zip):
            os.remove(out_zip)
        raise
    if not count and os.path.exists(out_zip):   # stopped, or nothing was added: no empty zip is left behind
        os.remove(out_zip)
    return count


# ---------- CreatePlugin: file helpers ----------
def rm_zips(folder):
    for f in glob(os.path.join(folder, "*.zip")):
        os.remove(f)


def rm_build_dirs(code_dir):
    for d in ("dist", "pkg"):
        rmtree_force(os.path.join(code_dir, d), ignore_errors=True)


def stash_files(code_dir, rels, stash, moved):
    """Move the chosen files out of the Code folder into `stash`. `moved` records progress,
    so a failure half way still leaves a full list of what needs putting back."""
    for rel in rels:
        src = os.path.join(code_dir, rel)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(stash, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        moved.append(rel)


def restore_files(code_dir, moved, stash, lines):
    """Put stashed files back. Never overwrites: if the build recreated a file, the
    stashed copy is kept and reported."""
    kept = False
    for rel in moved:
        dst = os.path.join(code_dir, rel)
        if os.path.exists(dst):
            lines.append(f"Not restored (already exists): {rel}")
            kept = True
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(os.path.join(stash, rel), dst)
    if kept:
        lines.append(f"Kept copies in {stash}")
    else:
        rmtree_force(stash, ignore_errors=True)
        if moved:
            lines.append("Restored the excluded files")


def clean_bloat(root):
    """Delete __pycache__ folders, *.pyc and *.log files."""
    for dirpath, dirnames, filenames in os.walk(root):
        for d in list(dirnames):
            if d == "__pycache__":
                p = os.path.join(dirpath, d)
                os.unlink(p) if os.path.islink(p) else rmtree_force(p, ignore_errors=True)
                dirnames.remove(d)
        for f in filenames:
            if f.endswith((".pyc", ".log")):
                os.unlink(os.path.join(dirpath, f))


# ---------- CreatePlugin: the job ----------
def run_plugin_job(lines, dwc_version, plugin, pver, exclude):
    job = plugin_job
    dwc_dir = os.path.join(dwc_versions_dir(), dwc_version)
    pvd = os.path.join(plugins_dir(), plugin, "plugin" + pver)  # plugin version dir
    code_dir = code_dir_for(plugin, pver)

    ok = False
    try:
        with open(os.path.join(code_dir, "plugin.json"), encoding="utf-8-sig") as f:
            manifest = json.load(f)
        this_version = manifest.get("version")
        if not this_version or not re.fullmatch(r"[0-9A-Za-z._+-]+", str(this_version)):
            raise ValueError("plugin.json has no usable 'version'")
        dwc_manifest = manifest.get("dwcVersion")
        lines.append(f"dwcVersion was reported as {'null' if dwc_manifest is None else dwc_manifest}")

        zip_file = f"{plugin}-{this_version}.zip"
        out_zip = os.path.join(pvd, f"{pver}-{zip_file}")

        if dwc_manifest is None:
            lines.append("No dwcVersion in manifest therefore do not need to build")
            lines.append(f"Zipping {plugin} v{pver} for DWC version {dwc_version}")
            if exclude:
                lines.append("Also excluding: " + ", ".join(exclude))
            rm_zips(pvd)
            lines.append(f"$ zip {out_zip}   (made by this app, no zip program needed)")
            count = zip_folder(job, lines, out_zip, code_dir, exclude)
            if count == 0:
                lines.append("Nothing to zip: every file was left out")
                if os.path.exists(out_zip):
                    os.remove(out_zip)
            ok = bool(count)
        else:
            lines.append("Cleaning out bloat and old builds")
            clean_bloat(pvd)
            rm_build_dirs(code_dir)
            lines.append(f"Build {plugin} v{pver} for DWC version {dwc_version}")
            stash, moved = None, []
            try:
                if exclude:
                    # Moved out of Code so the build cannot include them, and put back afterwards
                    stash = tempfile.mkdtemp(prefix=".excluded-", dir=pvd)
                    stash_files(code_dir, exclude, stash, moved)
                    lines.append("Kept out of this build (restored afterwards): " + ", ".join(moved))
                rm_zips(pvd)
                rm_zips(code_dir)
                # build-plugin.js must exist in the DWC version's ./scripts folder
                code = job.step(lines, ["node", "./scripts/build-plugin.js", code_dir], dwc_dir)
                if code == 0:
                    built = os.path.join(code_dir, zip_file)
                    if os.path.isfile(built):
                        lines.append(f"Move {built} to {out_zip}")
                        shutil.move(built, out_zip)
                        ok = True
                    else:
                        lines.append(f"Build finished but {built} was not created")
            finally:
                if stash:
                    restore_files(code_dir, moved, stash, lines)
                rm_build_dirs(code_dir)

        if ok and os.path.isfile(out_zip):
            st = os.stat(out_zip)
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
            lines.append("")
            lines.append("Resulting ZIP file")
            lines.append(f"{st.st_size:>10} bytes  {when}  {out_zip}")
    except Exception as e:
        lines.append(f"Error: {e}")
    finally:
        if job.stopping:
            lines.append("--- stopped ---")
        else:
            lines.append("--- finished OK ---" if ok else "--- FAILED ---")
        job.busy = False


# ---------- DWCVersion: the job ----------
def dev_script(version):
    """npm script that starts the dev server: 'dev' (Vite) from DWC 3.7 on, 'serve' (Vue CLI) before that."""
    m = re.match(r"(\d+)(?:\.(\d+))?", version)   # 3.5.1 -> (3, 5), 3.6-dev -> (3, 6), 3.10 -> (3, 10)
    major, minor = int(m.group(1)), int(m.group(2) or 0)
    return "dev" if (major, minor) >= (3, 7) else "serve"


def run_dwc_job(lines, version):
    """git clone -> npm install -> npm audit -> npm run dev, streaming output into `lines`."""
    job = dwc_job
    target = os.path.join(dwc_versions_dir(), version)
    code = None
    up_at = None   # set once the dev server answers HTTP 200
    try:
        lines.append(f"Create version v{version} in {target}")
        if os.path.isdir(target):
            lines.append("Removing existing folder")
            rmtree_force(target)
        os.makedirs(dwc_versions_dir(), exist_ok=True)

        code = job.step(lines, ["git", "clone", "--branch", "v" + version, REPO, target],
                        dwc_versions_dir(), title="Download version", env=GIT_ENV)
        if code == 0:
            code = job.step(lines, ["npm", "install"], target, title="Setup dev environment")
        if code == 0:
            # A non-zero exit here only means vulnerabilities were found, so carry on
            job.step(lines, ["npm", "audit", "--omit=dev"], target, title="Audit check")
            script = dev_script(version)
            code = job.serve(lines, ["npm", "run", script], target, title=f"Start the service (npm run {script})")
            if code == READY:
                up_at = job.service_url
    except Exception as e:  # e.g. folder could not be deleted
        lines.append(f"Error: {e}")
    finally:
        if up_at:
            lines.append(f"--- finished OK - dev server running at {up_at} (press Stop to shut it down) ---")
        elif job.stopping:
            lines.append("--- stopped ---")
        else:
            lines.append(f"--- finished (exit code {code}) ---")
        job.busy = False


# ---------- routes: shared ----------
def add_job_routes(prefix, name, job):
    """Stop and log endpoints for one tool."""
    def stop():
        if job.busy or job.service_running():
            job.terminate()
        return jsonify(ok=True)

    def log():
        return jsonify(job.view(int(request.args.get("from", 0)), int(request.args.get("run", 0))))

    app.add_url_rule(f"{prefix}/api/stop", f"{name}_stop", stop, methods=["POST"])
    app.add_url_rule(f"{prefix}/api/log", f"{name}_log", log, methods=["GET"])


add_job_routes("/createplugin", "plugin", plugin_job)
add_job_routes("/dwcversion", "dwc", dwc_job)


@app.get("/api/status")
def api_status():
    up = dwc_job.service_running()
    return jsonify(createplugin=plugin_job.busy, dwcversion=dwc_job.busy or up,
                   dev_url=dwc_job.service_url if up else "")


@app.post("/api/exit")
def api_exit():
    """Stop every running job, then shut down this web server."""
    def shutdown():
        for j in JOBS:
            j.terminate(force_after=5)
        for _ in range(50):  # let a job finish putting back any files it moved aside
            if not any(j.busy for j in JOBS):
                break
            time.sleep(0.1)
        os._exit(0)

    threading.Timer(0.5, shutdown).start()  # let this response reach the browser first
    return jsonify(ok=True)


def config_view():
    d, p = dwc_versions_dir(), plugins_dir()
    return {
        "dwc_versions_dir": d, "plugins_dir": p,
        "code_path": code_path(),
        "defaults": {"dwc_versions_dir": DEFAULT_DWC_VERSIONS, "plugins_dir": DEFAULT_PLUGINS,
                     "code_path": DEFAULT_CODE_PATH},
        "preferred_port": preferred_port(),
        "url": f"http://{HOST}:{PORT}/" if PORT else "",   # where this tool is listening right now
        "dwc_count": len(dwc_versions()) if os.path.isdir(d) else None,   # None = folder not found
        "plugin_count": sum(1 for x in subdirs(p) if plugin_versions(x)) if os.path.isdir(p) else None,
        "settings_file": SETTINGS_FILE,
        "first_run": not os.path.isfile(SETTINGS_FILE),
    }


@app.get("/api/config")
def api_config_get():
    return jsonify(config_view())


@app.post("/api/config")
def api_config_set():
    if any(j.busy for j in JOBS):
        return jsonify(error="A job is running - wait for it to finish or stop it first"), 409
    d = request.get_json(silent=True) or {}
    new = {}
    for key, label in (("dwc_versions_dir", "DWC versions folder"), ("plugins_dir", "Plugins folder")):
        raw = d.get(key, "")
        if not isinstance(raw, str):
            return jsonify(error=f"{label}: invalid value"), 400
        raw = raw.strip()
        if not raw:
            continue  # empty means "use the default"
        path = os.path.expanduser(raw)
        if not os.path.isabs(path):
            return jsonify(error=f"{label}: enter a full path, such as /home/pi/DWC or C:\\DWC"), 400
        path = os.path.normpath(path)
        if not os.path.isdir(path):
            return jsonify(error=f"{label}: '{path}' is not an existing folder"), 400
        if path != os.path.normpath(DEFAULTS[key]):
            new[key] = path   # the default is simply not stored, so it keeps following the install folder
    raw_code = d.get("code_path", "")
    if not isinstance(raw_code, str):
        return jsonify(error="Code folder: invalid value"), 400
    # Accept "/Code", "Code/" or "src\\Code": always stored as a relative path with forward slashes
    parts = [x for x in re.split(r"[\\/]+", raw_code.strip()) if x and x != "."]
    if ":" in raw_code or ".." in parts:
        return jsonify(error="Code folder: use a path relative to the plugin version folder, such as Code or src/Code"), 400
    if parts and "/".join(parts) != DEFAULT_CODE_PATH:
        new["code_path"] = "/".join(parts)   # empty or the default is simply not stored
    raw_port = d.get("preferred_port", 0)
    if isinstance(raw_port, str):
        raw_port = raw_port.strip() or "0"
    try:
        if isinstance(raw_port, float) and not raw_port.is_integer():
            raise ValueError
        port = int(raw_port)
    except (TypeError, ValueError):
        return jsonify(error="Preferred port: enter a whole number"), 400
    if isinstance(raw_port, bool) or (port != 0 and not 1024 <= port <= 65535):
        return jsonify(error="Preferred port: use 0 (no preference) or a port from 1024 to 65535"), 400
    if port:
        new["preferred_port"] = port   # 0 is the default, so it is simply not stored
    with save_lock:
        data = load_store()
        data["config"] = new
        err = write_store(data)
    if err:
        return jsonify(error=f"Could not save the settings file: {err}"), 500
    return jsonify(config_view())


# ---------- routes: CreatePlugin ----------
@app.get("/createplugin/api/options")
def plugin_options():
    plugins = []
    for p in subdirs(plugins_dir()):
        versions = plugin_versions(p)
        if versions:  # a folder without any plugin<version> folder is not a plugin
            plugins.append({"name": p, "versions": versions})
    return jsonify(dwc=dwc_versions(), plugins=plugins, last=saved_last("createplugin"))


@app.get("/createplugin/api/files")
def plugin_files():
    dwc = request.args.get("dwc", "")
    plugin = request.args.get("plugin", "")
    pver = request.args.get("version", "")
    if plugin not in subdirs(plugins_dir()) or pver not in plugin_versions(plugin):
        return jsonify(files=[], selected=[])
    listed = code_files(plugin, pver)
    # Only pre-tick remembered files that still exist
    selected = [f for f in saved_excludes(dwc, plugin, pver) if f in set(listed)]
    return jsonify(files=listed, selected=selected)


@app.post("/createplugin/api/start")
def plugin_start():
    d = request.get_json(silent=True) or {}
    dwc, plugin, pver = (str(d.get(k, "")).strip() for k in ("dwc", "plugin", "plugin_version"))
    exclude = d.get("exclude", [])
    # Only accept values that match real folders (also blocks path tricks)
    if dwc not in dwc_versions():
        return jsonify(error="Choose an existing DWC version"), 400
    if plugin not in subdirs(plugins_dir()):
        return jsonify(error="Choose an existing plugin"), 400
    if pver not in plugin_versions(plugin):
        return jsonify(error="Choose an existing plugin version"), 400
    if not isinstance(exclude, list) or not all(isinstance(x, str) for x in exclude):
        return jsonify(error="Invalid exclusion list"), 400
    if not set(exclude) <= set(code_files(plugin, pver)):
        return jsonify(error="An excluded file does not exist in the Code folder"), 400
    lines = plugin_job.begin()
    if lines is None:
        return jsonify(error="Already running - stop it first"), 409
    lines.append(f"Build: DWC {dwc}, plugin {plugin}, plugin version {pver}")
    err = remember_plugin_run(dwc, plugin, pver, exclude)
    if err:
        lines.append(f"Could not remember these selections: {err}")
    threading.Thread(target=run_plugin_job, args=(lines, dwc, plugin, pver, exclude), daemon=True).start()
    return jsonify(ok=True)


# ---------- routes: DWCVersion ----------
@app.get("/dwcversion/api/options")
def dwc_options():
    return jsonify(dwc=dwc_versions(), last=saved_last("dwcversion"))


@app.post("/dwcversion/api/start")
def dwc_start():
    version = str((request.get_json(silent=True) or {}).get("version", "")).strip()
    # The version becomes a folder name that gets deleted, so keep it strict. Starting with a digit
    # also means it can never name an ordinary folder (Documents, ...) or this script's own files when the folder is the install folder.
    if not VERSION_NAME.fullmatch(version):
        return jsonify(error="Invalid version: start with a digit, no leading 'v' (e.g. 3.5.1 or 3.6-dev)"), 400
    if dwc_job.service_running():
        return jsonify(error="The dev server is still running - press Stop first"), 409
    lines = dwc_job.begin()
    if lines is None:
        return jsonify(error="Already running - stop it first"), 409
    err = save_last("dwcversion", {"version": version})
    if err:
        lines.append(f"Could not remember this selection: {err}")
    threading.Thread(target=run_dwc_job, args=(lines, version), daemon=True).start()
    return jsonify(ok=True)


# ---------- pages ----------
TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
 body{font-family:system-ui,sans-serif;margin:1rem;max-width:60rem}
 input,select{padding:.5rem;font-size:1rem;margin:0 .5rem .5rem 0}
 input.v{width:12rem}
 button{padding:.5rem 1rem;font-size:1rem;cursor:pointer}
 .nav{margin-bottom:.5rem}
 #status{margin-left:.5rem;font-weight:600}
 #log{background:#111;color:#ddd;padding:.75rem;height:65vh;overflow:auto;white-space:pre-wrap;
      font:13px/1.4 ui-monospace,monospace;border-radius:6px;margin-top:1rem}
 details{margin:.25rem 0}
 summary{cursor:pointer;padding:.25rem 0}
 #exlist{max-height:14rem;overflow:auto;border:1px solid #888;border-radius:6px;padding:.5rem;margin-top:.25rem}
 #exlist label{display:block;font:13px ui-monospace,monospace}
 #exlist small{display:block;margin-bottom:.4rem;font:12px system-ui,sans-serif;opacity:.75}
 .cards{display:flex;gap:1rem;flex-wrap:wrap;margin:1rem 0}
 .card{flex:1 1 16rem;border:1px solid #888;border-radius:10px;padding:1rem 1.25rem;text-decoration:none;color:inherit}
 .card:hover{border-color:#2d7ff9}
 .card b{display:block;font-size:1.25rem;margin-bottom:.25rem}
 .card span{display:block;opacity:.8}
 .card em{display:block;font-style:normal;font-weight:600;min-height:1.2em;margin-top:.5rem}
 .field{margin:1rem 0}
 .field input{width:100%;box-sizing:border-box}
 .field input#pp{width:8rem}
 .note{font-size:.9rem;opacity:.8;min-height:1.2em}
 .bad{color:#c0392b;opacity:1}
 #msg{font-weight:600}
 .firstrun{border:1px solid #2d7ff9;border-radius:8px;padding:.6rem .9rem}
 .doc h3{margin:1.75rem 0 .5rem}
 .doc p,.doc li{line-height:1.5}
 .doc pre{background:#111;color:#ddd;padding:.75rem;border-radius:6px;overflow:auto;font:13px/1.4 ui-monospace,monospace}
 .doc code{font-family:ui-monospace,monospace;font-size:.95em}
 .doc table{border-collapse:collapse;margin:.5rem 0}
 .doc td,.doc th{border:1px solid #888;padding:.35rem .7rem;text-align:left;vertical-align:top}
</style></head><body>
__BODY__
<script>
__COMMON_JS__
__SCRIPT__
</script></body></html>"""

COMMON_JS = r"""
const $ = id => document.getElementById(id);
let closed = false;
async function post(url, body){
  const r = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body||{})});
  const j = await r.json(); if(!r.ok) alert(j.error); return j;
}
function wireExit(){
  $("exit").onclick = async () => {
    if(!confirm("Stop any running jobs and shut down this server?")) return;
    closed = true;
    await post("/api/exit");
    document.body.innerHTML = "<p>Server closed. You can close this tab.</p>";
  };
}
// Polls <api>/log and keeps the log box, status text and Start button up to date.
function startPolling(api, onFinished){
  let run = 0, n = 0, wasRunning = false;
  const logEl = $("log");
  async function poll(){
    if(closed) return;
    try{
      const j = await (await fetch(`${api}/log?run=${run}&from=${n}`)).json();
      if(j.run !== run){ run = j.run; logEl.textContent = ""; }
      if(j.lines.length){
        const atBottom = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 20;
        logEl.textContent += j.lines.join("\n") + "\n";
        if(atBottom) logEl.scrollTop = logEl.scrollHeight;
      }
      n = j.total;
      $("status").textContent = j.running ? "● running"
                              : j.service ? "● dev server running at " + j.service : "idle";
      $("go").disabled = j.running || !!j.service;
      if(wasRunning && !j.running && onFinished) onFinished();
      wasRunning = j.running;
    }catch(e){ if(!closed) $("status").textContent = "server unreachable"; }
    setTimeout(poll, 700);
  }
  poll();
}
"""


def render(title, body, script=""):
    return (TEMPLATE.replace("__TITLE__", title).replace("__BODY__", body)
            .replace("__SCRIPT__", script).replace("__COMMON_JS__", COMMON_JS))


HOME_PAGE = render("DWC tools", """
<h2>DWC tools</h2>
<div class="cards">
  <a class="card" href="/createplugin"><b>Create a Plugin</b>
    <span>Build or zip a DWC plugin</span><em id="s-createplugin"></em></a>
  <a class="card" href="/dwcversion"><b>Create DWC Version</b>
    <span>Clone a DWC version and start its dev server</span><em id="s-dwcversion"></em></a>
</div>
<button onclick="location.href='/settings'">Settings</button>
<button onclick="location.href='/readme'">Instructions</button>
<button id="exit">Exit</button>
""", r"""
wireExit();
async function status(){
  if(closed) return;
  try{
    const s = await (await fetch("/api/status")).json();
    $("s-createplugin").textContent = s.createplugin ? "● running" : "";
    $("s-dwcversion").textContent = !s.dwcversion ? "" : s.dev_url ? "● dev server running at " + s.dev_url : "● running";
  }catch(e){}
  setTimeout(status, 2000);
}
status();
""")

PLUGIN_PAGE = render("Create a Plugin", """
<div class="nav"><a href="/">&larr; Home</a> &middot; <a href="/readme">Instructions</a></div>
<h2>Create a Plugin</h2>
<label>DWC <select id="dwc"></select></label>
<label>Plugin <select id="pl"></select></label>
<label>Version <select id="pv"></select></label>
<button id="go">Build</button> <button id="stop">Stop</button>
<button id="exit">Exit</button> <button onclick="location.href='/settings'">Settings</button>
<span id="status"></span>
<details>
  <summary id="excount">Exclude files (0)</summary>
  <div id="exlist"></div>
</details>
<div id="log"></div>
""", r"""
const API = "/createplugin/api";
let opts = {dwc: [], plugins: []};
function fill(sel, items){
  sel.innerHTML = "";
  items.forEach(x => sel.add(new Option(x, x)));
}
function selected(){
  return [...document.querySelectorAll("#exlist input:checked")].map(c => c.value);
}
function updateCount(){ $("excount").textContent = `Exclude files (${selected().length})`; }
let loadSeq = 0;
async function loadFiles(){
  const my = ++loadSeq, enc = encodeURIComponent;
  const q = `dwc=${enc($("dwc").value)}&plugin=${enc($("pl").value)}&version=${enc($("pv").value)}`;
  const data = await (await fetch(`${API}/files?` + q)).json();
  if(my !== loadSeq) return;   // a newer selection has already replaced this one
  const files = data.files, on = new Set(data.selected);
  const box = $("exlist");
  box.innerHTML = "";
  const hint = document.createElement("small");
  hint.textContent = "Ticks are remembered for this DWC version + plugin + version. " +
    "Paths start at the Code folder. Zip-only builds: left out of the zip. " +
    "Real builds: moved out of Code during the build, then put back. " +
    "Always excluded: __pycache__, venv, *.log, *.pyc";
  box.append(hint);
  files.forEach(f => {
    const l = document.createElement("label"), c = document.createElement("input");
    c.type = "checkbox"; c.value = f; c.checked = on.has(f); c.onchange = updateCount;
    l.append(c, " " + f);   // text node, so file names are never treated as HTML
    box.append(l);
  });
  updateCount();
}
function syncVersions(pick){
  const p = opts.plugins.find(p => p.name === $("pl").value);
  const versions = p ? p.versions : [];
  fill($("pv"), versions);
  if(pick && versions.includes(pick)) $("pv").value = pick;
  loadFiles();
}
async function loadOpts(){
  opts = await (await fetch(`${API}/options`)).json();
  fill($("dwc"), opts.dwc);
  fill($("pl"), opts.plugins.map(p => p.name));
  // Start from what was used last time, as far as those folders still exist
  const last = opts.last || {};
  if(opts.dwc.includes(last.dwc)) $("dwc").value = last.dwc;
  if(opts.plugins.some(p => p.name === last.plugin)) $("pl").value = last.plugin;
  syncVersions(last.plugin_version);
}
$("dwc").onchange = loadFiles;
$("pl").onchange = () => syncVersions();
$("pv").onchange = loadFiles;
$("go").onclick = () => post(`${API}/start`, {
  dwc: $("dwc").value, plugin: $("pl").value, plugin_version: $("pv").value, exclude: selected()});
$("stop").onclick = () => post(`${API}/stop`);
wireExit();
loadOpts();
startPolling(API);
""")

DWC_PAGE = render("Create DWC Version", """
<div class="nav"><a href="/">&larr; Home</a> &middot; <a href="/readme">Instructions</a></div>
<h2>Create DWC Version</h2>
<select id="dwc"></select>
<input id="v" class="v" placeholder="3.5.1 or 3.6-dev" hidden>
<button id="go">Start</button> <button id="stop">Stop</button>
<button id="exit">Exit</button> <button onclick="location.href='/settings'">Settings</button>
<span id="status"></span>
<div id="log"></div>
""", r"""
const API = "/dwcversion/api";
let lastVersion = "";
function syncUI(){ $("v").hidden = $("dwc").value !== "__new"; }
async function loadOpts(keep){
  const data = await (await fetch(`${API}/options`)).json();
  const list = data.dwc, sel = $("dwc");
  const want = keep || (data.last || {}).version || "";   // this run's version, else last time's
  sel.innerHTML = "";
  list.forEach(x => sel.add(new Option(x, x)));
  sel.add(new Option("New version…", "__new"));
  if(want && list.includes(want)) sel.value = want;
  else if(want){ sel.value = "__new"; $("v").value = want; }   // not cloned (yet): keep what was typed
  else if(!list.length) sel.value = "__new";
  syncUI();
}
$("dwc").onchange = syncUI;
$("go").onclick = () => {
  const isNew = $("dwc").value === "__new";
  const version = isNew ? $("v").value.trim() : $("dwc").value;
  if(!isNew && !confirm(`This deletes and re-downloads the existing ${version} folder. Continue?`)) return;
  lastVersion = version;
  post(`${API}/start`, {version});
};
$("stop").onclick = () => post(`${API}/stop`);
wireExit();
loadOpts();
startPolling(API, () => loadOpts(lastVersion));   // a newly cloned version appears once the run ends
""")

SETTINGS_PAGE = render("DWC tools - Settings", """
<div class="nav"><a href="/">&larr; Home</a> &middot; <a href="/readme">Instructions</a></div>
<h2>Settings</h2>
<div class="field">
  <label for="dv"><b>DWC versions folder</b></label>
  <input id="dv" autocomplete="off">
  <div class="note" id="dvn"></div>
</div>
<div class="field">
  <label for="pd"><b>Plugins folder</b></label>
  <input id="pd" autocomplete="off">
  <div class="note" id="pdn"></div>
</div>
<p class="note">Folders must already exist. Enter a full path, such as <code>/home/pi/DWC</code> on Linux or <code>C:\\DWC</code> on Windows (<code>~</code> is fine too).
Until you change them, both show the folder this app is installed in (the default). Clear a box, or press Reset to defaults, to go back to it.
Create DWC Version puts new versions in the first folder; Create a Plugin reads the DWC versions from it and the plugins from the second.</p>
<div class="field">
  <label for="cp"><b>Code folder</b> inside each plugin version folder</label>
  <input id="cp" autocomplete="off">
  <div class="note">A relative path, not a full one: the folder holding <code>plugin.json</code>, inside <code>&lt;Plugins folder&gt;/&lt;plugin&gt;/plugin&lt;version&gt;</code>. Leave empty for the default, <code>Code</code> (a leading slash, as in <code>/Code</code>, is fine).</div>
</div>
<div class="field">
  <label for="pp"><b>Preferred port</b> for this tool's web page</label>
  <input id="pp" inputmode="numeric" autocomplete="off">
  <div class="note">0 means no preference: the first free port from 17800 is used. Otherwise use a port from 1024 to 65535.
  If your preferred port is already in use, the first free port from 17800 is used instead.
  A change takes effect the next time the app starts.</div>
  <div class="note" id="ppn"></div>
</div>
<button id="save">Save</button> <button id="reset">Reset to defaults</button> <span id="msg"></span>
<p class="note" id="file"></p>
""", r"""
function show(c){
  $("dv").value = c.dwc_versions_dir;   // always the folder in use, which is the install folder until changed
  $("pd").value = c.plugins_dir;
  $("cp").value = c.code_path === c.defaults.code_path ? "" : c.code_path;
  $("cp").placeholder = c.defaults.code_path;
  $("dv").placeholder = c.defaults.dwc_versions_dir;
  $("pd").placeholder = c.defaults.plugins_dir;
  const note = (el, path, count, what) => {
    el.className = count === null ? "note bad" : "note";
    el.textContent = count === null ? `In use: ${path} - folder not found`
                                    : `In use: ${path} - ${count} ${what} found`;
  };
  note($("dvn"), c.dwc_versions_dir, c.dwc_count, "DWC version folder(s)");
  note($("pdn"), c.plugins_dir, c.plugin_count, "plugin(s)");
  $("pp").value = c.preferred_port;
  $("ppn").textContent = c.url ? "This tool is running at " + c.url : "";
  $("file").textContent = "Stored in " + c.settings_file;
}
async function save(values, okText){
  const r = await fetch("/api/config", {method:"POST", headers:{"Content-Type":"application/json"},
                                        body: JSON.stringify(values)});
  const j = await r.json();
  $("msg").className = r.ok ? "" : "bad";
  $("msg").textContent = r.ok ? okText : j.error;
  if(r.ok) show(j);
}
$("save").onclick = () => save({dwc_versions_dir: $("dv").value, plugins_dir: $("pd").value,
                                code_path: $("cp").value, preferred_port: $("pp").value}, "Saved");
$("reset").onclick = () => save({dwc_versions_dir: "", plugins_dir: "", code_path: "", preferred_port: 0}, "Reset to defaults");
(async () => show(await (await fetch("/api/config")).json()))();
""")


_README_TEMPLATE = render("DWC tools - Instructions", """
<div class="nav"><a href="/">&larr; Home</a></div>
<div class="doc">
<h2>Instructions</h2>
<p class="firstrun" id="first-run" hidden>Welcome. No settings have been saved yet, so the DWC versions folder and the plugins
folder are both set to the folder this app is installed in (<code id="cur-script">...</code>). Open <a href="/settings">Settings</a> and point them at the right folders.</p>
<p>These tools help with DuetWebControl (DWC) plugin development on a Raspberry Pi or a Windows PC. There are two:</p>
<ul>
  <li><b>Create DWC Version</b> downloads a DWC release from GitHub, installs its dependencies and starts its dev server.</li>
  <li><b>Create a Plugin</b> builds or zips one of your plugins into an installable <code>.zip</code>.</li>
</ul>
<p>They run as separate jobs, so the DWC dev server can keep running while you build plugins.</p>

<h3>Setup</h3>
__SETUP__
<p>The app prints the address to use when it starts, and on a desktop session your browser opens there by itself.
It listens on this computer's network address (so <code>localhost</code> will not work) on the <b>preferred port</b> from the
<a href="/settings">Settings</a> page if that port is free, or otherwise on the first free port from 17800.
Any computer on the same network can open that address. There is no login, so anyone who can reach the page can run builds
and change the folders: only use it on a network you trust. This computer needs a network connection when the app starts, so that it has an address to use.</p>

<h3>Folders</h3>
<p>Both tools expect this layout. <b>Create a Plugin</b> only lists what is already there, and <b>Create DWC Version</b> creates the DWC version folders for you.
Until you set them on the Settings page, both folders are the folder this app is installed in, so a downloaded version such as <code>3.7</code> appears right next to <code>plugin_tools.py</code>. (That folder must be writable, or Create DWC Version cannot download into it: pick another folder in Settings if it isn't.) Only folders named like a DWC version (starting with a digit, such as
<code>3.5.1</code>) are listed as versions, and a plugin is listed once it has at least one <code>plugin&lt;version&gt;</code> folder.</p>
<pre>&lt;DWC versions folder&gt;/
    3.5.1/                    one folder per DWC version
    3.6-dev/
&lt;Plugins folder&gt;/
    &lt;plugin name&gt;/
        plugin1.2.3/          one folder per plugin version, named "plugin" + the version
            Code/         (the "Code folder" setting; Code by default)
                plugin.json   the plugin manifest
                ...           the plugin's files</pre>
<p>The Settings page also has the <b>Preferred port</b> for this tool's own web page. <code>0</code>, the default, means no preference:
the first free port from 17800 is used. A change takes effect the next time the app starts.
This tool is currently running at <code id="cur-url">...</code>.</p>
<p>Currently in use: DWC versions in <code id="cur-dwc">...</code>, plugins in <code id="cur-plugins">...</code>.
Change them on the <a href="/settings">Settings</a> page, for example if you move things to another disk.
Settings can't be changed while a job is running.</p>

<h3>Create DWC Version: get a DWC version running</h3>
<ol>
  <li>Choose a version in the list, or choose <b>New version&hellip;</b> and type one, such as <code>3.5.1</code> or <code>3.6-dev</code>.
      Start with a digit and do not type a leading <code>v</code>. It must match a release tag (<code>v3.5.1</code>) or branch on the
      <a href="https://github.com/Duet3D/DuetWebControl" target="_blank" rel="noopener">DuetWebControl repository</a>.</li>
  <li>Press <b>Start</b>. It runs <code>git clone</code>, <code>npm install</code>, <code>npm audit</code> and then the dev server, and shows the output as it goes.
      Audit findings are shown but don't stop the job. The dev server command depends on the version:
      <code>npm run dev</code> (Vite) for 3.7 and later, and <code>npm run serve</code> for older versions such as 3.5.1 or 3.6-dev.</li>
  <li>When the dev server prints its <code>Local:</code> address, the tool checks it with <code>curl</code>. As soon as it answers
      HTTP 200 the job is finished OK and the status shows where the server is running. It does not wait for
      any further bundling. The server keeps running, and the rest of its output keeps appearing in the log.
      The older servers print their address after the first compile has finished, which can take a while on a Pi.</li>
  <li>Press <b>Stop</b> to shut the dev server down. You can't start another version while it is running.</li>
</ol>
<p>Choosing a version that is already downloaded <b>deletes that folder and downloads it again</b>. You are asked to confirm first.
If the address doesn't answer 200 within 30 seconds, the log says so and the job just carries on waiting until the server exits or you press Stop.</p>

<h3>Create a Plugin: build or zip a plugin</h3>
<ol>
  <li>Choose the <b>DWC</b> version, the <b>Plugin</b> and its <b>Version</b>.</li>
  <li>Press <b>Build</b>. What happens depends on the plugin's <code>plugin.json</code>:
    <ul>
      <li><b>No <code>dwcVersion</code> entry</b> (for example a plugin that only runs on the Pi): the contents of <code>Code</code> are zipped. No build is needed.</li>
      <li><b><code>dwcVersion</code> present</b>: the plugin is built against the DWC version you chose, using that version's
          <code>scripts/build-plugin.js</code>. Old <code>dist</code> and <code>pkg</code> folders and any <code>__pycache__</code>, <code>*.pyc</code> and
          <code>*.log</code> files in the plugin version folder are cleared first.</li>
    </ul></li>
  <li>The result is written in the plugin version folder (the one containing <code>Code</code>) as
      <code>&lt;plugin version&gt;-&lt;plugin name&gt;-&lt;manifest version&gt;.zip</code>, and the log ends with its size and path.
      Any older <code>.zip</code> files in that folder are removed.</li>
</ol>

<h3>Leaving files out</h3>
<p>These are always left out of a zip: <code>__pycache__</code> and <code>venv</code> folders, <code>*.log</code> and <code>*.pyc</code> files.
To leave out more, open <b>Exclude files</b>, which lists every file under <code>Code</code>, and tick the ones you don't want.</p>
<ul>
  <li>For a zip-only plugin, ticked files are left out of the zip. Nothing on disk changes.</li>
  <li>For a real build, ticked files are moved out of <code>Code</code> while the build runs and put back afterwards, even if the build fails or you press Stop.</li>
  <li>Your ticks are remembered separately for each DWC version, plugin and plugin version combination.</li>
</ul>

<h3>What is remembered</h3>
<p>The selections you used last time in each tool come back as the defaults, the ticked files are remembered per combination (above),
and the two folders are kept until you change them. They are all stored in one settings file, which is currently
<code id="cur-file">...</code>.</p>
<p><b>Where the settings file is.</b> By default it is <code>.plugin_build_exclusions.json</code> in the same folder as <code>plugin_tools.py</code>. __HIDDEN_NOTE__ Things to know:</p>
<ul>
  <li>It is not created when the app first starts. It appears the first time you save on the Settings page or press Build or Start.
      Until the file exists, the app opens on this page.</li>
  <li>That folder must be writable, or nothing can be saved. The app warns at start-up if it isn't.</li>
  <li>If you move or copy the app to another folder, take the settings file with you.</li>
  <li>Moving your DWC versions or plugins folders does not move the file. Use Settings to point the tools at the new folders.</li>
  <li>It is plain text, so you can back it up or delete it. Deleting it resets everything to the defaults.</li>
</ul>

<h3>Stop and Exit</h3>
<ul>
  <li><b>Stop</b> ends the running job in that tool, including the dev server if it is running.</li>
  <li><b>Exit</b> stops everything and shuts the app down. Closing the browser tab does <b>not</b> stop it, so use Exit (or press Ctrl+C in the terminal) when you have finished.</li>
  <li>The Home page shows which tools are currently running.</li>
</ul>

<h3>If something goes wrong</h3>
<table>
  <tr><th>You see</th><th>Try</th></tr>
  __NOT_FOUND_ROW__
  <tr><td>The clone fails</td><td>Check the version exists as <code>v&lt;version&gt;</code> on GitHub, and that this computer has internet access</td></tr>
  <tr><td>"folder not found" on Settings</td><td>Correct the path, or clear the box to use the default</td></tr>
  <tr><td>The DWC or plugin list is empty on Create a Plugin</td><td>Check the folder layout above. A DWC version must be downloaded first with Create DWC Version</td></tr>
  <tr><td>The build fails straight away</td><td>The chosen DWC version needs <code>scripts/build-plugin.js</code>, and <code>plugin.json</code> needs a <code>version</code></td></tr>
  <tr><td>"Already running"</td><td>Wait for the job to finish, or press Stop</td></tr>
  <tr><td>The address is different from last time</td><td>The preferred port was in use (often another copy of this app), so the next free port from 17800 was used. Use Exit in the other copy, or look at the terminal for the address</td></tr>
  <tr><td>The app stops at start-up with "Unknown error trying to get the local IP address"</td><td>This computer has no network connection. Connect it by Ethernet or Wi-Fi and start the app again</td></tr>
__OS_ROWS__
</table>
</div>
""", r"""
(async () => {
  try{
    const c = await (await fetch("/api/config")).json();
    $("cur-dwc").textContent = c.dwc_versions_dir;
    $("cur-plugins").textContent = c.plugins_dir;
    $("cur-file").textContent = c.settings_file;
    $("cur-url").textContent = c.url;
    $("cur-script").textContent = c.defaults.dwc_versions_dir;   // the default folder = where this app is installed
    $("first-run").hidden = !c.first_run;
  }catch(e){}
})();
""")


def build_readme(is_windows):
    """The instructions page, with the setup steps, paths and examples for Windows or Linux."""
    if is_windows:
        text = {
            "__SETUP__": (
                '<p><b>Windows</b> (10 or later). Install Python 3.8 or later (from python.org, tick "Add python.exe to PATH"), '
                '<b>Git for Windows</b> (git-scm.com) and <b>Node.js</b> (nodejs.org, which includes npm). '
                'Then open Command Prompt or PowerShell and install Flask:</p>'
                '<pre>pip install flask</pre><p>Then start the app:</p><pre>python plugin_tools.py</pre>'
                '<p>No zip program is needed: the app makes zip files itself. Windows may ask whether to allow Python through '
                'the firewall. Allow it on private networks, or other computers will not be able to open the page.</p>'),
            "__HIDDEN_NOTE__": "The name starts with a dot, but Windows does not hide it: it shows in File Explorer like any other file.",
            "__NOT_FOUND_ROW__": '<tr><td>"Could not start git / npm / node"</td><td>Install Git for Windows or Node.js, '
                                 'then close and reopen the Command Prompt so that it finds them</td></tr>',
            "__OS_ROWS__": (
                '  <tr><td>Cloning or deleting fails with a "path too long" message</td><td>Node.js makes very deep folders. '
                r'Keep the DWC versions folder short (for example <code>C:\DWC</code>) or turn on long paths in Windows</td></tr>' '\n'
                '  <tr><td>Other computers cannot open the page</td><td>Allow Python through Windows Defender Firewall '
                'for private networks</td></tr>'),
        }
    else:
        text = {
            "__SETUP__": (
                '<p><b>Linux</b> (for example Raspberry Pi OS / Debian Trixie): install what the tools use:</p>'
                '<pre>sudo apt install python3-flask git nodejs npm</pre>'
                '<p>Then start the app from a terminal:</p><pre>python3 plugin_tools.py</pre>'
                '<p>No zip program is needed: the app makes zip files itself.</p>'),
            "__HIDDEN_NOTE__": "The name starts with a dot, so it is hidden: use <code>ls -a</code> in that folder to see it.",
            "__NOT_FOUND_ROW__": '<tr><td>"Could not start git / npm / node"</td><td>Install it: '
                                 '<code>sudo apt install git nodejs npm</code></td></tr>',
            "__OS_ROWS__": "",
        }
    page = _README_TEMPLATE
    for key, value in text.items():
        page = page.replace(key, value)
    return page


README_PAGE = build_readme(IS_WINDOWS)


@app.get("/readme")
def readme_page():
    return README_PAGE


@app.get("/")
def home():
    return HOME_PAGE


@app.get("/createplugin")
def createplugin_page():
    return PLUGIN_PAGE


@app.get("/dwcversion")
def dwcversion_page():
    return DWC_PAGE


@app.get("/settings")
def settings_page():
    return SETTINGS_PAGE


def open_browser(path="/"):
    # Only when a desktop session exists - on a headless Pi, Python could otherwise
    # launch a text browser inside the terminal
    if not IS_WINDOWS and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return
    host = "localhost" if HOST in ("0.0.0.0", "127.0.0.1", "::") else HOST
    webbrowser.open(f"http://{host}:{PORT}{path}")


def check_settings_writable():
    """Warn at start-up if settings cannot be saved where they are meant to live."""
    target = os.path.abspath(SETTINGS_FILE)
    if not os.path.exists(target):
        # Saving creates missing folders, so what matters is the nearest folder that already exists
        target = os.path.dirname(target)
        while not os.path.exists(target) and os.path.dirname(target) != target:
            target = os.path.dirname(target)
    if not os.access(target, os.W_OK):
        logger.warning(f"Settings cannot be saved: {target} is not writable. "
                       f"Install the app in a folder you can write to")


def main():
    global HOST, PORT
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    # Check which operating system this is running on (Linux and Windows are supported)
    logger.info(f"Running on {PLATFORM}" + (" (Windows code paths)" if IS_WINDOWS else ""))
    if PLATFORM not in ("Linux", "Windows"):
        logger.warning(f"{PLATFORM} has not been tested: it is being treated like Linux")
    logger.info(f"Settings file: {SETTINGS_FILE} ({'found' if os.path.isfile(SETTINGS_FILE) else 'not found'})")
    check_settings_writable()
    # Use the preferred port from the settings if it is free (else the first free port from 17800),
    # and from here on this tool's address and port are whatever validate_port() returned
    HOST, PORT = validate_port(preferred_port())
    # No settings file yet = first run: start on the instructions. Otherwise start on Home as normal.
    path = "/" if os.path.isfile(SETTINGS_FILE) else "/readme"
    host = "localhost" if HOST in ("0.0.0.0", "127.0.0.1", "::") else HOST
    print(f" * DWC tools: http://{host}:{PORT}{path}")
    threading.Timer(1.0, open_browser, args=(path,)).start()  # give the server a moment to start
    app.run(host=HOST, port=PORT, threaded=True)


if __name__ == "__main__":
    main()
