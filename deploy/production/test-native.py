"""Exercise the real release and systemd API with test paths under local Linux /opt."""

import argparse
from contextlib import contextmanager
from grp import getgrnam
from pathlib import Path
from pwd import getpwnam
from secrets import token_urlsafe
import os
import shutil
import socket
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from uuid import uuid4

PRODUCTION = Path(__file__).resolve().parent


def execute(*args, cwd=None, env=None):
    return subprocess.run(args, cwd=cwd, env=env, check=True)


@contextmanager
def isolated_api(name):
    try:
        yield
    finally:
        subprocess.run(["systemctl", "stop", name], check=False, capture_output=True)
        subprocess.run(["systemctl", "reset-failed", name], check=False, capture_output=True)


def smoke(release, wheelhouse, interpreter, nginx):
    owner, group = getpwnam("nobody"), getgrnam("nogroup")
    with TemporaryDirectory(prefix="fooddiary-phase72-", dir="/opt") as directory:
        root = Path(directory)
        root.chmod(0o755)
        share = root / "shared"
        backups = root / "backups"
        key_dir = share / "config"
        data, media = share / "data", share / "media"
        for path in (data, media):
            path.mkdir(parents=True)
            os.chown(path, owner.pw_uid, group.gr_gid)
            path.chmod(0o700)
        key_dir.mkdir()
        os.chown(key_dir, 0, group.gr_gid)
        key_dir.chmod(0o750)
        backups.mkdir(mode=0o700)
        env_file = key_dir / "fooddiary.env"
        database = data / "fooddiary.db"
        env_file.write_text(
            f'APP_ENV=production\nAPP_ORIGINS=\'["https://food.example"]\'\n'
            f'JWT_SECRET={token_urlsafe(48)}\nDATABASE_URL=sqlite:///{database}\nMEDIA_DIR={media}\n'
            'PUBLIC_REGISTRATION=false\nAI_ENABLED=false\nSTICKER_ENABLED=false\n'
        )
        os.chown(env_file, 0, group.gr_gid)
        env_file.chmod(0o640)
        revision = (release / "REVISION").read_text().strip()
        installed = root / "releases" / revision
        shutil.copytree(release, installed)
        command_dir = root / "commands"
        command_dir.mkdir()
        (command_dir / "nginx").symlink_to(nginx)
        env = {**os.environ, "PATH": f"{command_dir}:{os.environ['PATH']}", "PYTHON_BIN": str(interpreter)}
        prepare = root / "prepare.sh"
        prepare.write_text((PRODUCTION / "prepare.sh").read_text().replace("/opt/fooddiary", str(root))
                           .replace("root:fooddiary", "root:nogroup").replace("runuser -u fooddiary", "runuser -u nobody"))
        execute("bash", prepare, "release", revision, wheelhouse, env=env)
        python = installed / "backend/.venv/bin/python"
        backend = installed / "backend"
        candidate = data / ".candidate-fixture.db"
        candidate.touch()
        os.chown(candidate, owner.pw_uid, group.gr_gid)
        execute("runuser", "-u", "nobody", "--", python, "-m", "app.maintenance", "migrate-candidate", candidate, cwd=backend)
        candidate.rename(database)
        (root / "current").symlink_to(installed)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = str(listener.getsockname()[1])
        name = f"fooddiary-review-{uuid4().hex[:8]}.service"
        health = root / "health.sh"
        health.write_text((PRODUCTION / "health.sh").read_text().replace("/opt/fooddiary", str(root))
                          .replace("fooddiary-api.service", name).replace("18080", port))
        for unit in PRODUCTION.glob("fooddiary-*"):
            if unit.suffix not in (".service", ".timer"):
                continue
            formatted = (unit.read_text().replace("/opt/fooddiary", str(root))
                         .replace("/.sticker/bin/python", "/.venv/bin/python")
                         .replace("User=fooddiary", "User=nobody").replace("Group=fooddiary", "Group=nogroup"))
            (root / unit.name).write_text(formatted)
        execute("systemd-analyze", "verify", *sorted(root.glob("*.service")), *sorted(root.glob("*.timer")))
        with isolated_api(name):
            execute("systemd-run", "--quiet", "--unit", name,
                    "-p", "User=nobody", "-p", "Group=nogroup", "-p", f"WorkingDirectory={backend}",
                    "-p", f"EnvironmentFile={env_file}", "-p", "PrivateTmp=true", "-p", "ProtectHome=true",
                    "-p", "ProtectSystem=strict", "-p", "NoNewPrivileges=true", "-p", f"ReadWritePaths={data} {media}",
                    python, "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "127.0.0.1", "--port", port)
            deadline = monotonic() + 60
            while True:
                result = subprocess.run(["bash", health, "local", revision], capture_output=True, text=True)
                if not result.returncode:
                    break
                if monotonic() >= deadline:
                    subprocess.run(["journalctl", "-u", name, "-n", "20", "--no-pager"])
                    subprocess.run(["ss", "-H", "-lntp", f"sport = :{port}"])
                    raise RuntimeError("Real Linux API did not become healthy: " + result.stderr)
                sleep(.5)
            incorrect = subprocess.run(["bash", health, "local", "f" * 40], capture_output=True)
            assert incorrect.returncode
            print(result.stdout.strip())
        recovery = backups / "daily-20261128T043000-1"
        execute(python, "-m", "app.maintenance", "--reserve-bytes", "0", "backup",
                database, media, recovery, "--release", revision, cwd=backend)
        execute(python, "-m", "app.maintenance", "verify", recovery, cwd=backend)
        restored = backups / "restored"
        execute(python, "-m", "app.maintenance", "--reserve-bytes", "0", "restore", recovery, restored, cwd=backend)
        execute(python, "-m", "app.maintenance", "check-db", restored / "data/fooddiary.db", cwd=backend)
        print("Native package preparation, least-privilege systemd, health identity, backup and isolated re-open passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("release", "wheelhouse", "interpreter", "nginx"):
        parser.add_argument(name, type=Path)
    values = parser.parse_args()
    smoke(*(path.resolve(strict=True) for path in vars(values).values()))
