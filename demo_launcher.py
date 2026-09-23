"""Local demo bootstrap; uses the unchanged app and bundled case data."""
import argparse
import hashlib
import importlib.metadata
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent


def ensure_packages():
    requirements = ROOT / "requirements.txt"
    signature = hashlib.sha256(
        requirements.read_bytes() + sys.executable.encode() + sys.version.encode()
    ).hexdigest()
    marker = ROOT / "output" / ".demo-dependencies"
    installed = True
    # Current requirements contain plain distribution names, one per line.
    for package in requirements.read_text(encoding="utf-8").splitlines():
        if package.strip() and not package.startswith("#"):
            try:
                importlib.metadata.version(package.strip())
            except (importlib.metadata.PackageNotFoundError, ValueError):
                installed = False
    if installed and marker.exists() and marker.read_text() == signature:
        print("Dependencies are ready.", flush=True)
        return
    print("Installing/checking dependencies. Internet is needed on first setup...", flush=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(requirements)],
        check=True,
    )
    marker.parent.mkdir(exist_ok=True)
    marker.write_text(signature)


def open_when_ready(url, process):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(120):
        if process.poll() is not None:
            return
        try:
            with opener.open(url + "/_stcore/health", timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true", help="Print the URL without opening a browser")
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10 or newer is required.")
    os.chdir(ROOT)
    for path in (ROOT / "app.py", ROOT / "requirements.txt", ROOT / "data" / "se_manager_sheet.xlsx"):
        if not path.exists():
            raise RuntimeError("Missing " + str(path.name) + ". Extract/download the entire repository first.")
    if sys.platform == "darwin":
        venv_python = ROOT / "venv" / "bin" / "python"
        if Path(sys.prefix).resolve() != (ROOT / "venv").resolve():
            if not venv_python.exists():
                print("Creating local Mac environment (venv)...", flush=True)
                subprocess.run([sys.executable, "-m", "venv", str(ROOT / "venv")], check=True)
            return subprocess.call([str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]])
    ensure_packages()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    url = "http://127.0.0.1:" + str(port)
    print("\nLogix demo: " + url, flush=True)
    print("Keep this window open. First calculation may take about a minute. Stop: Ctrl+C.", flush=True)
    process = subprocess.Popen([
        sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
        "--server.address=127.0.0.1", "--server.port=" + str(port),
        "--server.headless=true", "--browser.gatherUsageStats=false",
    ])
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(url, process), daemon=True).start()
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print("\nDemo could not start: " + str(error), file=sys.stderr)
        print("See README.md for manual setup. No company data has been changed.", file=sys.stderr)
        sys.exit(1)
