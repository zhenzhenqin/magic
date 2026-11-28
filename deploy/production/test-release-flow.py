"""Run production Bash orchestration on Linux with controlled service transitions."""

from contextlib import contextmanager
from pathlib import Path
import json
import os
import subprocess
from tempfile import TemporaryDirectory

PRODUCTION = Path(__file__).resolve().parent
OLD, NEW = "1" * 40, "2" * 40
UNITS = ["fooddiary-api.service", "fooddiary-sticker.service", "fooddiary-ai.service"]

COMMAND = r'''#!/usr/bin/python3
import json, os, pathlib, shutil, signal, sys
from pathlib import Path
base = Path(os.environ["FLOW_ROOT"])
app = base / "app"
record = base / "running.json"
active = json.loads(record.read_text())
mode = os.environ.get("FLOW_FAILURE")
current = app / "current"
revision = current.resolve().name if current.is_symlink() else ""
db = app / "shared/data/fooddiary.db"
tool, *args = sys.argv
name = Path(tool).name
if name == "systemctl":
    action, unit, *_ = args
    if action == "is-active":
        sys.exit(0 if args[-1] in active else 1)
    if action == "show":
        print((1234 if unit in active else 0) if "MainPID" in args else ("active" if unit in active else "inactive"))
    if action in ("start", "stop"):
        with (base / "sequence").open("a") as log:
            print(action, revision, *args[1:], file=log)
        if action == "stop":
            active = [x for x in active if x not in args[1:]]
        else:
            active = list(set(active + args[1:]))
        record.write_text(json.dumps(active))
        if action == "start" and revision == "2" * 40 and mode == "interrupt":
            os.kill(os.getppid(), signal.SIGKILL)
elif name == "ss":
    print('LISTEN 0 1024 127.0.0.1:18080 0.0.0.0:* users:(("python",pid=1234,fd=6))')
elif name == "curl":
    if "--resolve" in args:
        print("X-FoodDiary-Maintenance: 1\r\n\r\n503" if mode != "no-maintenance" else "HTTP/1.1 200 OK\r\n\r\n200")
    else:
        if mode in ("wrong-revision", "old-wont-start") and revision == "2" * 40:
            print("X-FoodDiary-Revision: " + "9" * 40 + "\r\n\r\n200")
        elif mode == "old-wont-start" and revision == "1" * 40:
            print("HTTP/1.1 500 Error\r\n\r\n500")
        else:
            print("X-FoodDiary-Revision: " + revision + "\r\n\r\n200")
elif name == "runuser":
    os.execv(args[3], args[3:])
elif name == "install":
    if "-o" in args:
        args = args[:2] + args[6:]
    os.execv("/usr/bin/install", ["/usr/bin/install", *args])
elif name == "python":
    if args[0] == "-c":
        print("food.example")
    elif args[0] == "-m":
        command, *rest = args[2:]
        if command == "backup":
            target = Path(rest[2])
            target.mkdir()
            shutil.copyfile(rest[0], target / "fooddiary.db")
        elif command == "verify":
            assert (Path(rest[0]) / "fooddiary.db").is_file()
        elif command == "migrate-candidate":
            if mode == "migration":
                sys.exit(1)
            Path(rest[0]).write_text("candidate-db")
        elif command == "worker-ready" and mode == "worker" and revision == "2" * 40:
            sys.exit(1)
'''


@contextmanager
def lab(existing=False):
    with TemporaryDirectory(prefix="fooddiary-release-flow-") as folder:
        root = Path(folder)
        app = root / "app"
        state = app / "shared/logs/active-operation"
        marker = app / "shared/maintenance"
        db = app / "shared/data/fooddiary.db"
        backups = root / "backups"
        commands = root / "commands"
        for path in (db.parent, state.parent, app / "shared/media", backups, commands):
            path.mkdir(parents=True)
        (root / "running.json").write_text(json.dumps(UNITS if existing else []))
        (root / "sequence").touch()
        for tool in ("systemctl", "ss", "curl", "runuser", "install", "nginx", "sleep"):
            script = commands / tool
            script.write_text(COMMAND)
            script.chmod(0o755)
        for revision in (OLD, NEW):
            release = app / "releases" / revision
            executable = release / "backend/.venv/bin/python"
            executable.parent.mkdir(parents=True)
            executable.write_text(COMMAND)
            executable.chmod(0o755)
            (release / "web").mkdir()
            (release / "web/index.html").touch()
            (release / "REVISION").write_text(revision)
            (release / ".env").symlink_to(app / "shared/config/fooddiary.env")
            scripts = release / "deploy/production"
            scripts.mkdir(parents=True)
            (scripts / "health.sh").write_text((PRODUCTION / "health.sh").read_text().replace("/opt/fooddiary", str(app)))
        manage = root / "manage.sh"
        manage.write_text((PRODUCTION / "manage.sh").read_text()
                          .replace("/opt/fooddiary", str(app)).replace("/var/backups/fooddiary", str(backups)))
        if existing:
            db.write_text("old-db")
            (app / "current").symlink_to(app / "releases" / OLD)

        def run(*args, failure="none"):
            env = {**os.environ, "PATH": f"{commands}:{os.environ['PATH']}", "FLOW_ROOT": str(root), "FLOW_FAILURE": failure}
            return subprocess.run(["bash", manage, *args], env=env, capture_output=True, text=True, timeout=25)

        yield run, root, app / "current", db, marker, state


def verify():
    assert os.geteuid() == 0, "Run as root in an isolated Linux development environment."
    with lab() as (run, root, link, db, marker, state):
        assert run("publish", NEW, failure="wrong-revision").returncode
        assert marker.exists() and state.exists() and not link.is_symlink() and not db.exists()
        good = run("publish", NEW)
        assert good.returncode == 0, good.stderr
        assert link.resolve().name == NEW and db.read_text() == "candidate-db" and not marker.exists()
        before = (root / "sequence").read_text()
        assert run("publish", NEW).returncode == 0 and (root / "sequence").read_text() == before
    for failure in ("migration", "wrong-revision", "worker", "no-maintenance"):
        with lab(True) as (run, root, link, db, marker, state):
            failed = run("publish", NEW, failure=failure)
            assert failed.returncode, failure
            assert link.resolve().name == OLD and db.read_text() == "old-db", failed.stderr
            assert not marker.exists() and not state.exists(), failed.stderr
            if failure == "no-maintenance":
                assert not (root / "sequence").read_text()
            if failure == "worker":
                log = (root / "sequence").read_text()
                assert f"stop {NEW} " + " ".join(UNITS) in log
    with lab(True) as (run, root, link, db, marker, state):
        assert run("publish", NEW, failure="old-wont-start").returncode
        assert marker.exists() and state.exists() and link.resolve().name == OLD and db.read_text() == "old-db"
        assert run("recover").returncode == 0 and not marker.exists()
    with lab(True) as (run, root, link, db, marker, state):
        assert run("publish", NEW, failure="interrupt").returncode == -9
        assert marker.exists() and state.exists() and link.resolve().name == NEW
        assert run("publish", NEW).returncode
        assert run("recover").returncode == 0 and not marker.exists() and link.resolve().name == OLD
        assert db.read_text() == "old-db"
    print("Linux release orchestration: first start, idempotency, preflight, migration, writer quiescence, unhealthy rollback and SIGKILL recovery passed")


if __name__ == "__main__":
    verify()
