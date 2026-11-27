"""Run local CPU benchmarks on opaque, licensed or original test photographs."""
import argparse
import ctypes
import json
import os
import sys
from pathlib import Path
from time import perf_counter, process_time

from PIL import Image

from app.services.sticker_image import OnnxBackgroundRemovalProvider, StickerImageError, encode, make_sticker


def memory():
    if sys.platform == "win32":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (field, ctypes.c_size_t) for field in (
                    "peak", "working", "pool_peak", "pool_used", "nonpaged_peak", "nonpaged",
                    "pagefile", "pagefile_peak",
                )
            ]

        info = Counters()
        info.cb = ctypes.sizeof(Counters)
        ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        if not ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(info), info.cb):
            raise OSError("Cannot read process memory")
        return dict(rss=info.working, peak_rss=info.peak)
    values = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(("VmRSS:", "VmHWM:")):
            key, amount, _ = line.split()
            values["rss" if key == "VmRSS:" else "peak_rss"] = int(amount) * 1024
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--edges", type=int, nargs="+", default=[512, 768, 1024])
    args = parser.parse_args()
    directory, output, model_dir = (path.resolve() for path in (args.input, args.output, args.model_dir))
    if os.name == "nt" and any(path.drive.upper() != "D:" for path in (directory, output, model_dir)):
        parser.error("Use D: for images, weights and outputs")
    photos = sorted(directory.glob("*.jpg"))
    if not photos:
        parser.error("No JPEG files were found")
    output.mkdir(parents=True, exist_ok=True)
    before = memory()
    started = perf_counter()
    provider = OnnxBackgroundRemovalProvider(model_dir, 1)
    summary = dict(cold_ms=round((perf_counter() - started) * 1000), before=before, idle=memory(),
                   providers=provider.session.get_providers(), runs=[])
    for edge in args.edges:
        batch_start = perf_counter()
        batch_cpu = process_time()
        rows = []
        for photo in photos:
            start, cpu = perf_counter(), process_time()
            row = dict(case=photo.stem)
            try:
                with Image.open(photo, formats=["JPEG"]) as image:
                    row["source"] = image.size
                    output_images = make_sticker(image, edge, provider)
                for label, result in (("cutout", output_images.cutout), ("sticker", output_images.sticker)):
                    data = encode(result)
                    (output / f"{photo.stem}-{edge}-{label}.webp").write_bytes(data)
                    row[label + "_bytes"] = len(data)
                row["dimensions"] = output_images.sticker.size
                row["status"] = "succeeded"
            except StickerImageError as error:
                row["status"] = str(error)
            row.update(ms=round((perf_counter() - start) * 1000), cpu_ms=round((process_time() - cpu) * 1000))
            rows.append(row)
        elapsed = perf_counter() - batch_start
        summary["runs"].append(dict(edge=edge, ms=round(elapsed * 1000),
                                    cpu_percent_of_one_core=round((process_time() - batch_cpu) / elapsed * 100, 1),
                                    memory=memory(), samples=rows))
    (output / "performance.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"photos": len(photos), "edges": args.edges, "cold_ms": summary["cold_ms"], "memory": memory()}))


if __name__ == "__main__":
    main()
