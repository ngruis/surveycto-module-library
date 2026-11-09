from __future__ import annotations

import os
import socket
import sys

from streamlit.web import cli as streamlit_cli

from surveycto_module_library.config import load_settings


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def main() -> int:
    settings = load_settings()
    app_path = settings.root / "app" / "streamlit_app.py"
    if not app_path.exists():
        raise RuntimeError(f"The application interface is missing: {app_path}")

    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    port = _available_port()
    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.headless=false",
        "--global.developmentMode=false",
        "--browser.serverAddress=localhost",
        "--browser.gatherUsageStats=false",
    ]
    return int(streamlit_cli.main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
