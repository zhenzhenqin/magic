"""Launch an isolated, loopback API for the browser tests."""

from pathlib import Path
from tempfile import gettempdir, mkdtemp
import sys

import uvicorn

from app.main import create_app
from tests.support import isolated_settings, migrate


def main():
    backend_port, frontend_port = map(int, sys.argv[1:3])
    temp = Path(gettempdir()).resolve()
    if sys.platform == "win32" and temp.drive.upper() != "D:":
        raise ValueError("Run the browser tests with the D: environment script.")
    root = Path(mkdtemp(prefix="fooddiary-auth-browser-", dir=temp))
    settings = isolated_settings(
        root / "browser-test.db", app_origins=[f"http://127.0.0.1:{frontend_port}"],
        access_token_seconds=4, refresh_token_seconds=12, register_attempts=100,
        login_attempts=100, refresh_attempts=150,
    )
    migrate(settings)
    print(f"Test database: {root}", flush=True)
    uvicorn.run(create_app(settings), host="127.0.0.1", port=backend_port, proxy_headers=False)


if __name__ == "__main__":
    main()
