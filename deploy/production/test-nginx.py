"""Loopback smoke test of the production Nginx template on Linux."""

import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from socket import socket
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
from time import sleep


class Upstream(BaseHTTPRequestHandler):
    calls = 0

    def do_GET(self):
        self.answer(0)

    def do_POST(self):
        self.answer(len(self.rfile.read(int(self.headers.get("Content-Length", 0)))))

    def answer(self, size):
        Upstream.calls += 1
        body = json.dumps({"size": size, "forwarded": self.headers.get("X-Forwarded-For"), "call": Upstream.calls}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


@contextmanager
def upstream():
    with ThreadingHTTPServer(("127.0.0.1", 0), Upstream) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            yield server.server_port
        finally:
            server.shutdown()
            thread.join()


def ports():
    with socket() as a, socket() as b:
        a.bind(("127.0.0.1", 0))
        b.bind(("127.0.0.1", 0))
        return a.getsockname()[1], b.getsockname()[1]


def check(config_dir, root, binary, upstream_port):
    host = "food.example"
    http, https = ports()
    cert, key = root / "localhost.crt", root / "localhost.key"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=" + host,
         "-addext", "subjectAltName=DNS:" + host, "-keyout", key, "-out", cert],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    web = root / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<title>isolated fixture</title>")
    (web / "assets" / "index-testingA.js").write_text("export {};")
    (root / "shared").mkdir()
    (root / "shared" / "media").mkdir()
    (root / "shared" / "media" / "private.webp").write_bytes(b"private test file")
    site = root / "site.conf"
    subprocess.run(["python3", config_dir / "render-nginx.py", host, cert, key, site], check=True)
    source = site.read_text().replace("listen 80;", f"listen 127.0.0.1:{http};").replace(
        "listen 443 ssl;", f"listen 127.0.0.1:{https} ssl;",
    ).replace("https://food.example$request_uri", f"https://food.example:{https}$request_uri").replace(
        "/opt/fooddiary/current/web", str(web),
    ).replace("/opt/fooddiary/shared/", str(root / "shared") + "/").replace(
        "/etc/nginx/fooddiary/security.conf", str(config_dir / "nginx-security.conf"),
    ).replace("127.0.0.1:18080", f"127.0.0.1:{upstream_port}")
    site.write_text(source)
    config = root / "nginx.conf"
    temporary = "\n".join(f"{kind}_temp_path {root}/{kind};" for kind in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi"))
    config.write_text(
        f"pid {root}/nginx.pid;\nerror_log {root}/error.log;\nevents {{}}\nhttp {{\n"
        f"{temporary}\naccess_log off;\ninclude {site};\n}}\n",
    )
    command = [binary, "-p", str(root) + "/", "-c", config]
    subprocess.run([*command, "-t"], check=True)

    def call(path, *, plain=False, body=None, headers=()):
        scheme, port = ("http", http) if plain else ("https", https)
        curl = ["curl", "--noproxy", "*", "--max-time", "8", "--silent", "--show-error",
                "--cacert", cert, "--resolve", f"{host}:{port}:127.0.0.1",
                "--dump-header", "-", f"{scheme}://{host}:{port}{path}"]
        if body is not None:
            curl += ["--data-binary", "@-"]
        for header in headers:
            curl += ["-H", header]
        output = subprocess.run(curl, input=body, capture_output=True, check=True).stdout
        blocks = output.split(b"\r\n\r\n")
        raw, content = blocks[-2:]
        lines = raw.decode().splitlines()
        response = dict((k.lower(), v.strip()) for k, v in (line.split(":", 1) for line in lines[1:]))
        return int(lines[0].split()[1]), response, content

    process = subprocess.Popen([*command, "-g", "daemon off; master_process off;"])
    try:
        for _ in range(30):
            try:
                if call("/friends/example/diary")[0] == 200:
                    break
            except subprocess.CalledProcessError:
                sleep(.1)
        else:
            raise RuntimeError("Test Nginx did not start")
        assert call("/", plain=True)[0] == 308
        assert call("/api/v1/auth/login", plain=True, body=b"fixture")[0] == 405
        page_headers = call("/friends/example/diary")[1]
        assert page_headers["cache-control"] == "no-store"
        assert page_headers["permissions-policy"] == "camera=(self), microphone=(), geolocation=()"
        assert "media-src 'self' blob:" in page_headers["content-security-policy"]
        assert "img-src 'self' blob: data:" in page_headers["content-security-policy"]
        assert "immutable" in call("/assets/index-testingA.js")[1]["cache-control"]
        assert call("/assets/extra-xxxxxxxx.js")[0] == 404
        assert call("/assets/extra-xxxxxxxx.js")[1]["cache-control"] == "no-store"
        assert call("/media/private.webp")[0] == 404
        for path in ("/api/v1/auth/login", "/api/v1/friends", "/api/v1/media/shared/sticker"):
            first = call(path, headers=("X-Forwarded-For: 203.0.113.4",))
            second = call(path)
            assert first[0] == second[0] == 200
            assert first[1]["cache-control"] == second[1]["cache-control"] == "no-store"
            assert "strict-transport-security" in first[1]
            assert json.loads(first[2])["forwarded"] == "127.0.0.1"
            assert json.loads(first[2])["call"] != json.loads(second[2])["call"]
        assert json.loads(call("/api/v1/media/upload", body=b"x" * 1024)[2])["size"] == 1024
        denied = call("/api/v1/media/upload", body=b"x" * 10616833, headers=("Expect: 100-continue",))
        assert denied[0] == 413 and denied[1]["cache-control"] == "no-store"
        (root / "shared" / "maintenance").touch()
        maintenance = call("/api/v1/ready")
        assert maintenance[0] == 503 and maintenance[1]["x-fooddiary-maintenance"] == "1" and call("/")[0] == 503
        print("Nginx template: TLS, redirects, SPA/assets, private responses, trusted forwarding, 413 and maintenance passed")
    finally:
        process.terminate()
        process.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nginx", type=Path, required=True)
    parser.add_argument("--temp", type=Path, required=True)
    args = parser.parse_args()
    with TemporaryDirectory(dir=args.temp.resolve()) as folder, upstream() as port:
        check(Path(__file__).resolve().parent, Path(folder), args.nginx.resolve(), port)
