"""Write or verify the exact immutable content of a FoodDiary release."""

import argparse
from hashlib import file_digest
from pathlib import Path
import re

MANIFEST = "SHA256SUMS"
STAGED = ("backend", "deploy", "web")


def inventory(root, prepared=False):
    marker = root / "REVISION"
    names = set(STAGED) | {marker.name, MANIFEST}
    if prepared:
        names.add(".env")
    if any(path.name not in names for path in root.iterdir()):
        raise ValueError("Unexpected top-level release entry")
    files = [marker]
    for name in STAGED:
        folder = root / name
        if not folder.is_dir() or folder.is_symlink():
            raise ValueError("Expected an immutable release directory")
        files.extend(folder.rglob("*"))
    result = {}
    for path in files:
        key = path.relative_to(root).as_posix()
        parts = key.split("/")
        if prepared and parts[0] == "backend" and (parts[1:2] in ([".venv"], [".sticker"]) or "__pycache__" in parts):
            continue
        if path.is_symlink() or not re.fullmatch(r"[a-zA-Z0-9_./-]+", key):
            raise ValueError("Unexpected linked or invalid release path")
        if path.is_dir():
            continue
        with path.open("rb") as stream:
            result[key] = file_digest(stream, "sha256").hexdigest()
    # Sort POSIX path strings so Windows and Linux write identical inventories.
    return "".join(f"{digest}  {key}\n" for key, digest in sorted(result.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("write", "verify"))
    parser.add_argument("root", type=Path)
    parser.add_argument("revision")
    parser.add_argument("--prepared", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    marker = root / "REVISION"
    if not re.fullmatch(r"[a-f0-9]{40}", args.revision) or marker.is_symlink() or marker.read_text().strip() != args.revision:
        raise ValueError("Release revision does not match the selected Git SHA")
    manifest = root / MANIFEST
    content = inventory(root, args.prepared)
    if args.action == "write":
        with manifest.open("x", encoding="ascii", newline="\n") as output:
            output.write(content)
    elif manifest.is_symlink() or manifest.read_text(encoding="ascii") != content:
        raise ValueError("Release checksum or its file list differs")
    print(f"Verified release {args.revision}: {len(content.splitlines())} files")


if __name__ == "__main__":
    main()
