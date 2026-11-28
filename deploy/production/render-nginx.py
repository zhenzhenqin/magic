"""Write a project virtual-host config for review, with no installation side effects."""

import argparse
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
import re

LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
SAFE_PATH = re.compile(r"/[a-zA-Z0-9_/.-]+")
PRIVATE_NETWORKS = tuple(map(IPv4Network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10")))


def host_name(value):
    value = value.lower()
    labels = value.split(".")
    if all(part.isdecimal() for part in labels):
        return str(IPv4Address(value))
    if len(value) <= 253 and len(labels) > 1 and all(LABEL.fullmatch(part) for part in labels):
        return value
    raise ValueError("Use an ASCII DNS name or the verified public IPv4 address")


def private_address(value):
    address = IPv4Address(value)
    if not any(address in network for network in PRIVATE_NETWORKS):
        raise ValueError("The private listener needs an RFC 1918 or RFC 6598 IPv4 address")
    return address


def render(host, certificate, key, private_ip=None):
    host = host_name(host)
    if any(not SAFE_PATH.fullmatch(path) or ".." in Path(path).parts for path in (certificate, key)):
        raise ValueError("Use exact absolute paths for the certificate and key")
    template = Path(__file__).with_name("nginx.site.example").read_text(encoding="utf-8")
    if private_ip is not None:
        address = private_address(private_ip)
        _, marker, template = template.partition("# HTTPS virtual host\n")
        listener = "    listen 443 ssl;"
        if not marker or template.count(listener) != 1:
            raise ValueError("Unexpected HTTPS template layout")
        template = template.replace(listener, f"    listen {address}:443 ssl bind;\n    listen 127.0.0.1:443 ssl bind;")
    return template.replace("@HOST@", host).replace("@CERT@", certificate).replace("@KEY@", key)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host")
    parser.add_argument("certificate")
    parser.add_argument("key")
    parser.add_argument("output", type=Path)
    parser.add_argument("--private-ip", help="Bind only this private IPv4 address and loopback, without HTTP")
    args = parser.parse_args()
    try:
        config = render(args.host, args.certificate, args.key, args.private_ip)
    except ValueError as error:
        parser.error(str(error))
    with args.output.open("x", encoding="utf-8", newline="\n") as file:
        file.write(config)
