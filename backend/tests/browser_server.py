"""Launch an isolated, loopback API for the browser tests."""

import asyncio
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from tempfile import gettempdir, mkdtemp
import sys

import uvicorn
from PIL import Image

from app.main import create_app
from app.services.ai_provider import FakeVisionProvider, ProviderError
from app.services.ai_worker import AiWorker
from tests.support import isolated_settings, migrate


class BrowserVisionProvider(FakeVisionProvider):
    async def analyze(self, images):
        await asyncio.sleep(2.5)
        with Image.open(BytesIO(images[0])) as image:
            red, green, blue = image.getpixel((0, 0))
        if blue > 220 and red < 20 and green < 20:
            raise ProviderError("ai_invalid_result")
        return await super().analyze(images)


def main():
    backend_port, frontend_port = map(int, sys.argv[1:3])
    temp = Path(gettempdir()).resolve()
    if sys.platform == "win32" and temp.drive.upper() != "D:":
        raise ValueError("Run the browser tests with the D: environment script.")
    root = Path(mkdtemp(prefix="fooddiary-api-browser-", dir=temp))
    simulated = "--fake-ai" in sys.argv[3:]
    offline = "--no-ai-worker" in sys.argv[3:]
    settings = isolated_settings(
        root / "browser-test.db", app_origins=[f"http://127.0.0.1:{frontend_port}"],
        access_token_seconds=4, refresh_token_seconds=12, register_attempts=100,
        login_attempts=100, refresh_attempts=150,
        ai_enabled=simulated, ai_provider="fake" if simulated else "qwen",
        ai_user_daily_limit=3 if "--phase-41" in sys.argv[3:] else 1, ai_global_daily_limit=100,
    )
    migrate(settings)
    print(f"Test database: {root}", flush=True)
    app = create_app(settings)
    if simulated and not offline:
        original = app.router.lifespan_context

        @asynccontextmanager
        async def lifespan(application):
            async with original(application):
                worker = AiWorker(settings, app.state.session_factory, BrowserVisionProvider())
                await asyncio.to_thread(worker.heartbeat)
                task = asyncio.create_task(worker.run())
                try:
                    yield
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

        app.router.lifespan_context = lifespan
    uvicorn.run(app, host="127.0.0.1", port=backend_port, proxy_headers=False)


if __name__ == "__main__":
    main()
