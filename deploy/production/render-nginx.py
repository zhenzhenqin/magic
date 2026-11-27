"""Write a project virtual-host config for review, with no installation side effects."""

import argparse
from ipaddress import IPv4Address
from pathlib import Path
import re

LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
SAFE_PATH = re.compile(r"/[a-zA-Z0-9_/.-]+")


def host_name(value):
    value = value.lower()
    labels = value.split(".")
    if all(part.isdecimal() for part in labels):
        return str(IPv4Address(value))
    if len(value) <= 253 and len(labels) > 1 and all(LABEL.fullmatch(part) for part in labels):
        return value
    raise ValueError("Use an ASCII DNS name or the verified public IPv4 address")


def render(host, certificate, key):
    host = host_name(host)
    if any(not SAFE_PATH.fullmatch(path) or ".." in Path(path).parts for path in (certificate, key)):
        raise ValueError("Use exact absolute paths for the certificate and key")
    template = Path(__file__).with_name("nginx.site.example").read_text(encoding="utf-8")
    return template.replace("@HOST@", host).replace("@CERT@", certificate).replace("@KEY@", key)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    parser.add_argument("certificate")
    parser.add_argument("key")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    config = render(args.host, args.certificate, args.key)
    with args.output.open("x", encoding="utf-8", newline="\n") as file:
        file.write(config)
