from concurrent.futures import ThreadPoolExecutor
from secrets import token_urlsafe
from statistics import median
from time import perf_counter
from threading import Event

from app.core.config import Settings
from app.core.exceptions import ApiError
from app.core.security import Passwords


def main():
    settings = Settings(_env_file=None, app_env="test", jwt_secret=token_urlsafe(48))
    passwords = Passwords(settings)
    password = token_urlsafe(24)
    hashed = passwords.hash(password)
    measurements = []
    for _ in range(8):
        started = perf_counter()
        assert passwords.verify(password, hashed)
        measurements.append((perf_counter() - started) * 1000)
    print(f"Argon2id: m={settings.argon_memory_kib} KiB, t={settings.argon_time_cost}, p=1")
    print(f"8 verification runs: median {median(measurements):.1f} ms, max {max(measurements):.1f} ms")

    ready = [Event() for _ in range(settings.argon_slots)]
    release = Event()

    def occupy_slot(started):
        started.set()
        release.wait(timeout=5)

    with ThreadPoolExecutor() as pool:
        futures = [pool.submit(passwords._bounded, occupy_slot, event) for event in ready]
        try:
            assert all(event.wait(timeout=5) for event in ready)
            try:
                passwords.verify(password, hashed)
            except ApiError as error:
                assert error.status == 429
                print(f"Concurrency: {settings.argon_slots} active slots, excess rejected with 429")
            else:
                raise AssertionError("Expected the work limit to reject another hash")
        finally:
            release.set()
            for work in futures:
                work.result()


if __name__ == "__main__":
    main()
