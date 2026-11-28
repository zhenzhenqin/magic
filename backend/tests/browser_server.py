"""Launch an isolated, loopback API for the browser tests."""

import asyncio
from contextlib import asynccontextmanager
from io import BytesIO
from hashlib import sha256
import os
from pathlib import Path
from secrets import token_urlsafe
from tempfile import gettempdir, mkdtemp
import sys
import time

import uvicorn
from PIL import Image

from app.main import create_app
from app.schemas import Registration
from app.services.ai_provider import FakeVisionProvider, ProviderError
from app.services.ai_worker import AiWorker
from app.services.email_provider import CaptureEmailProvider
from app.services.auth import add_user
from app.services.sticker_image import StickerImageError
from app.services.sticker_worker import StickerWorker
from tests.support import isolated_settings, migrate


class BrowserVisionProvider(FakeVisionProvider):
    async def analyze(self, images):
        await asyncio.sleep(2.5)
        with Image.open(BytesIO(images[0])) as image:
            red, green, blue = image.getpixel((0, 0))
        if blue > 220 and red < 20 and green < 20:
            raise ProviderError("ai_invalid_result")
        return await super().analyze(images)


class FileTestInbox(CaptureEmailProvider):
    def __init__(self, directory):
        super().__init__()
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def send(self, email, purpose, code):
        super().send(email, purpose, code)
        name = sha256(email.encode()).hexdigest() + ".txt"
        (self.directory / name).write_text(code, encoding="ascii")


def main():
    backend_port, frontend_port = map(int, sys.argv[1:3])
    temp = Path(gettempdir()).resolve()
    if sys.platform == "win32" and temp.drive.upper() != "D:":
        raise ValueError("Run the browser tests with the D: environment script.")
    root = Path(mkdtemp(prefix="fooddiary-api-browser-", dir=temp))
    simulated = "--fake-ai" in sys.argv[3:]
    offline = "--no-ai-worker" in sys.argv[3:]
    sticker_tests = "--fake-stickers" in sys.argv[3:]
    real_stickers = "--onnx-stickers" in sys.argv[3:]
    personal = "--phase-73" in sys.argv[3:]
    if real_stickers and sticker_tests:
        raise ValueError("Choose one sticker mode")
    stable_session = simulated or sticker_tests or real_stickers or personal
    model = Path(os.environ["FOODDIARY_STICKER_MODEL"]).resolve() if real_stickers else root / "models"
    settings = isolated_settings(
        root / "browser-test.db", app_origins=[f"http://127.0.0.1:{frontend_port}"],
        access_token_seconds=120 if stable_session else 4,
        refresh_token_seconds=600 if stable_session else 12, register_attempts=100,
        login_attempts=100, refresh_attempts=150,
        ai_enabled=simulated or personal, ai_provider="fake" if simulated or personal else "qwen",
        ai_byok_simulation=personal,
        ai_user_daily_limit=3 if "--phase-41" in sys.argv[3:] else 1, ai_global_daily_limit=100,
        sticker_enabled=sticker_tests or real_stickers, sticker_provider="fake" if sticker_tests else "onnx",
        sticker_model_dir=model, email_mode="capture" if personal else "disabled",
        email_code_secret=token_urlsafe(48) if personal else None,
    )
    migrate(settings)
    print(f"Test database: {root}", flush=True)
    app = create_app(settings)
    if personal:
        inbox = Path(os.environ["FOODDIARY_TEST_INBOX"]).resolve()
        if sys.platform == "win32" and inbox.drive.upper() != "D:":
            raise ValueError("Test inbox must be on D:")
        app.state.mailer = FileTestInbox(inbox)
        with app.state.session_factory.begin() as db:
            password = "phase73-browser-fixture-only"
            data = Registration(username="phase73_reader", nickname="阅读搭子", password=password)
            add_user(db, data, app.state.passwords.hash(password), email="reader@example.test")
    if (simulated and not offline) or sticker_tests or real_stickers:
        original = app.router.lifespan_context

        @asynccontextmanager
        async def lifespan(application):
            async with original(application):
                tasks = []
                if simulated and not offline:
                    worker = AiWorker(settings, app.state.session_factory, BrowserVisionProvider())
                    await asyncio.to_thread(worker.heartbeat)
                    tasks.append(asyncio.create_task(worker.run()))
                if sticker_tests or real_stickers:
                    stickers = StickerWorker(settings, app.state.session_factory)
                    if sticker_tests:
                        normal = stickers.processor

                        def delayed(data, crop, tick):
                            time.sleep(2.0)
                            with Image.open(BytesIO(data)) as image:
                                red, green, blue = image.convert("RGB").getpixel((0, 0))
                            if not crop and blue > 220 and red < 20 and green < 20:
                                raise StickerImageError("foreground_uncertain")
                            return normal(data, crop, tick)

                        stickers.processor = delayed
                        await asyncio.to_thread(stickers.heartbeat)
                    else:
                        await asyncio.to_thread(stickers.warm)
                    async def run_stickers():
                        while True:
                            if not await asyncio.to_thread(stickers.run_once):
                                await asyncio.sleep(.5)
                    tasks.append(asyncio.create_task(run_stickers()))
                try:
                    yield
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    if sticker_tests or real_stickers:
                        await asyncio.to_thread(stickers.close)

        app.router.lifespan_context = lifespan
    uvicorn.run(app, host="127.0.0.1", port=backend_port, proxy_headers=False)


if __name__ == "__main__":
    main()
