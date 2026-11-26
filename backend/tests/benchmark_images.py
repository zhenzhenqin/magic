"""Measure the same media encoder in a fresh local process."""

from pathlib import Path
from secrets import token_urlsafe
from statistics import median
from tempfile import mkdtemp
from time import perf_counter
import subprocess
import sys

from PIL import Image

from app.core.config import Settings
from app.services.storage import LocalStorageProvider


def memory():
    if sys.platform != "win32":
        import resource

        return 0, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "peak", "working", "quota_peak_paged", "quota_paged", "quota_peak_nonpaged",
                "quota_nonpaged", "pagefile", "peak_pagefile",
            )
        ]

    data = Counters()
    data.size = ctypes.sizeof(data)
    if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(-1), ctypes.byref(data), data.size):
        raise OSError("Unable to measure process memory")
    return data.working, data.peak


def measure(source: Path):
    settings = Settings(_env_file=None, app_env="test", media_dir=source.parent, jwt_secret=token_urlsafe(48))
    provider = LocalStorageProvider(settings)
    before, _ = memory()
    results = []
    original, thumbnail = source.parent / "normalized.webp", source.parent / "thumbnail.webp"
    for _ in range(5):
        start = perf_counter()
        with source.open("rb") as file:
            dimensions = provider._encode(file, original, thumbnail)
        results.append((perf_counter() - start) * 1000)
    _, peak = memory()
    print(f"D: synthetic JPEG 4000x3000 ({source.stat().st_size} B); normalized {dimensions}, "
          f"{original.stat().st_size} B; thumbnail {thumbnail.stat().st_size} B")
    print(f"5 runs; median {median(results):.1f} ms; max {max(results):.1f} ms")
    print(f"Process working set before {before / 1048576:.1f} MiB; peak {peak / 1048576:.1f} MiB")


if __name__ == "__main__":
    if len(sys.argv) == 2:
        measure(Path(sys.argv[1]))
    else:
        root = Path(mkdtemp(prefix="fooddiary-image-benchmark-"))
        fixture = root / "synthetic-meal.jpg"
        with Image.effect_noise((4000, 3000), 34) as image:
            image.save(fixture, "JPEG", quality=86)
        subprocess.run([sys.executable, "-m", "tests.benchmark_images", str(fixture)], check=True)
