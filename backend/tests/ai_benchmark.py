"""Validate the public benchmark set and optionally exercise a local FoodDiary API."""

import argparse
import csv
import getpass
import json
import os
import re
import sqlite3
import time
from collections import Counter
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
from PIL import Image

from app.ai_schemas import RecognitionView
from app.core.config import BACKEND_DIR, Settings

ROOT = BACKEND_DIR.parent
MANIFEST = ROOT / "docs" / "ai-benchmark" / "cases.json"
FIELDS = (
    "case", "focus", "model", "region", "image_count", "expected_status", "expected_foods", "job_id", "result_status",
    "recognized_foods", "missing", "wrong", "duplicate", "json_valid", "end_to_end_ms", "provider_elapsed_ms",
    "input_tokens", "output_tokens", "usage_known", "nutrition_review", "attempt_statuses", "failure_retry_reasons",
    "upstream_request_ids", "estimate_amount", "estimate_currency", "price_reference", "billed_amount", "billed_currency",
    "billing_reference", "human_review",
)


def dataset():
    cases = json.loads(MANIFEST.read_text(encoding="utf-8"))
    seen = set()
    images = set()
    for case in cases:
        if case["case"] in seen or not 1 <= len(case["photos"]) <= 3:
            raise ValueError("Invalid case or photo count")
        seen.add(case["case"])
        for name in case["photos"]:
            path = (ROOT / name).resolve()
            if not path.is_relative_to(ROOT):
                raise ValueError("Fixtures must stay inside FoodDiary")
            with Image.open(path) as image:
                if image.format not in {"JPEG", "PNG", "WEBP"} or (min(image.size) < 64 or image.getexif()):
                    raise ValueError("Expected a supported, public metadata-free image")
                image.verify()
            images.add(path)
    if not 10 <= len(images) <= 15:
        raise ValueError("Expected 10–15 unique images")
    return cases, len(images)


def initial_row(case):
    return dict(case=case["case"], focus=case["focus"], image_count=len(case["photos"]),
                expected_status=" / ".join(case["status"]),
                expected_foods="、".join(group[0] for group in case["foods"]))


def spreadsheet_row(row):
    return {name: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
            for name, value in row.items()}


def compare(case, status, names):
    normalized = {alias: group[0] for group in case["foods"] for alias in group}
    counts = Counter(normalized.get(name, name) for name in names)
    required = {group[0] for group in case["foods"]} if status == "recognized" or case["status"] == ["recognized"] else set()
    return dict(missing="、".join(sorted(required - counts.keys())),
                wrong="、".join(sorted(counts.keys() - required)),
                duplicate="、".join(sorted(name for name, count in counts.items() if count > 1)))


class LocalApi:
    def __init__(self, client: httpx.Client, origin: str, username: str):
        self.client = client
        self.origin = origin
        self.username = username
        self.password = os.environ.get("FOODDIARY_BENCH_PASSWORD") or getpass.getpass("FoodDiary local test account password: ")
        self.authenticate()

    def authenticate(self):
        data = {"username": self.username, "password": self.password}
        response = self.client.post("/api/v1/auth/login", json=data,
                                    headers={"Origin": self.origin, "X-FoodDiary-Intent": "browser"})
        response.raise_for_status()
        self.token = response.json()["access_token"]

    def send(self, method, path, *, key=None, **options):
        headers = {"Authorization": "Bearer " + self.token}
        if key:
            headers["Idempotency-Key"] = key
        response = self.client.request(method, "/api/v1" + path, headers=headers, **options)
        if response.status_code == 401:
            self.authenticate()
            headers["Authorization"] = "Bearer " + self.token
            response = self.client.request(method, "/api/v1" + path, headers=headers, **options)
        return response

    def create_job(self, media, consent):
        key = uuid4().hex
        result = None
        try:
            response = self.send("POST", "/ai/jobs", key=key, json={"media_ids": media, "consent_version": consent})
            if response.status_code < 500:
                response.raise_for_status()
                result = response.json()
        except httpx.TransportError:
            pass
        if result is None:
            lookup = self.send("GET", "/ai/jobs/recover", params={"request_key": key})
            lookup.raise_for_status()
            result = lookup.json()
            if result is None:
                raise RuntimeError("Task creation was inconclusive. Inspect local recovery before another run.")
        return result


def attempts(connection, job_id):
    return connection.execute(
        "SELECT model, status, error_code, elapsed_ms, input_tokens, output_tokens, "
        "upstream_request_id, usage_known FROM ai_usage_logs WHERE job_id = ? ORDER BY created_at",
        (job_id,),
    ).fetchall()


def record_attempts(row, records, args):
    row["attempt_statuses"] = " / ".join(record["status"] for record in records)
    row["failure_retry_reasons"] = " / ".join(filter(None, [
        *(record["error_code"] for record in records), row.get("failure_retry_reasons"),
    ]))
    row["upstream_request_ids"] = " / ".join(record["upstream_request_id"] for record in records if record["upstream_request_id"])
    row["provider_elapsed_ms"] = " / ".join(str(record["elapsed_ms"]) for record in records if record["elapsed_ms"] is not None)
    sent = [record for record in records if record["status"] not in ("reserved", "not_sent")]
    if sent:
        row["model"] = sent[-1]["model"]
    known = bool(sent) and all(record["usage_known"] for record in sent)
    row["usage_known"] = known
    row["input_tokens"] = " / ".join(str(record["input_tokens"]) if record["input_tokens"] is not None else "未知" for record in sent)
    row["output_tokens"] = " / ".join(str(record["output_tokens"]) if record["output_tokens"] is not None else "未知" for record in sent)
    if known and args.input_price is not None and args.output_price is not None:
        estimate = sum(record["input_tokens"] * args.input_price + record["output_tokens"] * args.output_price for record in sent)
        row.update(estimate_amount=estimate / 1_000_000, estimate_currency=args.currency, price_reference=args.price_reference)


def run_cases(api, connection, cases, args):
    response = api.send("GET", "/ai/capabilities")
    response.raise_for_status()
    cap = response.json()
    if not (cap["available"] and cap["worker_online"]) or cap["simulated"] != (args.run_local == "fake"):
        raise RuntimeError("Expected a ready local Worker with the selected provider")
    estimate_total = Decimal(0)
    for case in cases:
        row = initial_row(case) | {"region": args.region or "offline-fixture"}
        response = api.send("GET", "/ai/usage")
        response.raise_for_status()
        if not response.json()["available"]:
            row["failure_retry_reasons"] = response.json()["exhausted_reason"]
            yield row
            break
        photo_ids = []
        for name in case["photos"]:
            path = ROOT / name
            with path.open("rb") as source:
                uploaded = api.send("POST", "/media/upload", files={"file": (path.name, source)})
            uploaded.raise_for_status()
            photo_ids.append(uploaded.json()["id"])
        now = time.monotonic()
        job = api.create_job(photo_ids, cap["consent_version"])
        while job["status"] in ("pending", "running"):
            if time.monotonic() - now > 930 or not job["worker_online"]:
                raise RuntimeError("Worker stopped or task timed out. Check the existing task before retrying.")
            time.sleep(1.5)
            response = api.send("GET", "/ai/jobs/" + job["id"])
            response.raise_for_status()
            job = response.json()
        row.update(job_id=job["id"], result_status=job["status"], end_to_end_ms=round((time.monotonic() - now) * 1000),
                   failure_retry_reasons=job["error_code"] or "", json_valid="否" if job["error_code"] == "ai_invalid_result" else "")
        if job["result"] is not None:
            recognition = RecognitionView.model_validate(job["result"])
            names = [food.food_name for food in recognition.foods]
            row.update(result_status=recognition.status, recognized_foods="、".join(names), json_valid="是",
                       **compare(case, recognition.status, names))
        record_attempts(row, attempts(connection, job["id"]), args)
        yield row
        if args.run_local == "qwen":
            estimate_total += row.get("estimate_amount", 0)
            if estimate_total >= args.approved_budget:
                break


def options():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-local", choices=["fake", "qwen"], help="Default validates images without network calls")
    parser.add_argument("--base-url", default="http://127.0.0.1:15175", help="Local Vite proxy origin")
    parser.add_argument("--database", type=Path, help="SQLite file used by the local API")
    parser.add_argument("--username", help="Dedicated, already registered local test account")
    parser.add_argument("--output", type=Path, help="CSV path. Existing files are preserved.")
    parser.add_argument("--cases", nargs="+", help="Select case IDs")
    parser.add_argument("--region")
    parser.add_argument("--authorized-attempts", type=int)
    parser.add_argument("--approved-budget", type=Decimal, help="Operator-confirmed amount in the selected currency")
    parser.add_argument("--input-price", type=Decimal, help="Price per million input tokens")
    parser.add_argument("--output-price", type=Decimal, help="Price per million output tokens")
    parser.add_argument("--currency")
    parser.add_argument("--price-reference", help="A verified regional price card and tier")
    return parser, parser.parse_args()


def main():
    parser, args = options()
    cases, image_count = dataset()
    if args.cases:
        if set(args.cases) - {case["case"] for case in cases}:
            parser.error("Unknown case")
        cases = [case for case in cases if case["case"] in args.cases]
    if not args.run_local and not args.output:
        print(f"Validated {image_count} public fixtures; {len(cases)} selected cases. No network calls.")
        return
    if not args.output or (os.name == "nt" and args.output.resolve().drive.upper() != "D:"):
        parser.error("Provide a new CSV output path on D: in Windows")
    if args.output.exists():
        parser.error("CSV already exists")
    if not args.run_local:
        with args.output.open("x", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(initial_row(case) for case in cases)
        return
    if not args.username or not args.database or not re.fullmatch(r"http://127\.0\.0\.1:[0-9]{2,5}", args.base_url):
        parser.error("A dedicated test account, read-only SQLite location and loopback origin are required")
    database = args.database.resolve(strict=True)
    if os.name == "nt" and database.drive.upper() != "D:":
        parser.error("Use the isolated FoodDiary SQLite file on D:")
    if args.run_local == "qwen":
        settings = Settings()
        price = (args.input_price, args.output_price)
        host = httpx.URL(settings.ai_base_url).host
        public_regions = {"dashscope.aliyuncs.com": "cn-beijing", "dashscope-intl.aliyuncs.com": "ap-southeast-1",
                          "cn-hongkong.dashscope.aliyuncs.com": "cn-hongkong"}
        region = public_regions.get(host) or (host.split(".")[1] if host.endswith(".maas.aliyuncs.com") else None)
        if (not args.region or args.region != region or args.approved_budget is None
                or not args.approved_budget.is_finite() or args.approved_budget <= 0
                or not args.authorized_attempts or args.authorized_attempts <= 0
                or not args.currency or not args.price_reference or any(value is None or not value.is_finite() or value < 0 for value in price)
                or settings.ai_provider != "qwen" or not settings.ai_available or settings.ai_model != "qwen3-vl-flash"
                or Path(settings.db_url.database).resolve() != database):
            parser.error("Real execution needs the approved attempts, budget, region, price card and matching Flash-only settings")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as ledger:
        ledger.row_factory = sqlite3.Row
        if args.run_local == "qwen":
            (spent,) = ledger.execute("SELECT spent FROM ai_call_budgets WHERE provider = 'qwen'").fetchone()
            if not len(cases) <= settings.ai_qwen_cumulative_limit - spent <= args.authorized_attempts:
                parser.error("Set the application's remaining cumulative slots within the confirmed attempt allowance")
        with httpx.Client(base_url=args.base_url, trust_env=False, follow_redirects=False, timeout=60) as client:
            api = LocalApi(client, args.base_url, args.username)
            with args.output.open("x", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                writer.writeheader()
                for row in run_cases(api, ledger, cases, args):
                    writer.writerow(spreadsheet_row(row))
                    stream.flush()
                    print(f"{row['case']}: {row.get('result_status') or '未执行'}")


if __name__ == "__main__":
    main()
