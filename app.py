import csv
import io
import os
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

BASE_URL = os.getenv("BASE_URL", "http://tempnumbers.net").rstrip("/")
USERNAME = os.getenv("TEMP_NUMBERS_USERNAME", "")
PASSWORD = os.getenv("TEMP_NUMBERS_PASSWORD", "")
POLL_INTERVAL = max(5, int(os.getenv("POLL_INTERVAL_SECONDS", "30")))
REQUEST_TIMEOUT = max(5, int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")))

USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Linux; Android 10; K) Chrome/130.0.0.0 Mobile Safari/537.36",
)
OUTPUT_HEADER = [
    "Date", "Range", "Number", "CLI", "Client", "SMS", "Currency",
    "My Payout", "Client Payout",
]

session = requests.Session()
session_lock = threading.Lock()
seen_sms: set[tuple[str, ...]] = set()
latest_records: list[list[str]] = []
last_poll_at: str | None = None
last_error: str | None = None
poller_started = False


def parse_csv_line(line: str) -> list[str]:
    try:
        return next(csv.reader(io.StringIO(line), skipinitialspace=True))
    except (csv.Error, StopIteration):
        return []


def is_timestamp_line(line: str) -> bool:
    return bool(re.match(r'^\s*"?\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}"?,', line))


def normalize_record(record: list[Any]) -> list[str] | None:
    if not record:
        return None
    record = [str(value) for value in record[:9]]
    record += [""] * (9 - len(record))
    for i in range(9):
        if i != 5:
            record[i] = record[i].strip()

    if not re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}$", record[0]):
        return None
    if not record[2] or not record[5]:
        return None
    return record


def rebuild_record(lines: list[str]) -> list[str] | None:
    if not lines:
        return None
    first = parse_csv_line(lines[0])
    if not first:
        return None
    if len(first) >= 9:
        return normalize_record(first)
    if len(first) < 6:
        return None

    record = first[:6]
    sms_parts = [str(first[5])]
    currency = my_payout = client_payout = ""
    for continuation in lines[1:]:
        row = parse_csv_line(continuation)
        if not row:
            continue
        if len(row) >= 4:
            sms_parts.append(str(row[0]))
            currency = str(row[1]).strip()
            my_payout = str(row[2]).strip()
            client_payout = str(row[3]).strip()
        else:
            sms_parts.extend(str(value) for value in row)

    record[5] = "\n".join(value for value in sms_parts if value != "")
    record.extend([currency, my_payout, client_payout])
    return normalize_record(record)


def process_sms(data: str) -> list[list[str]]:
    lines = data.lstrip("\ufeff").splitlines()
    if not lines:
        return []

    start_index = 0
    for i, line in enumerate(lines):
        normalized = [value.strip().lower() for value in parse_csv_line(line)]
        if "date" in normalized and "number" in normalized and "sms" in normalized:
            start_index = i + 1
            break

    records: list[list[str]] = []
    current_record: list[str] = []
    for line in lines[start_index:]:
        if not line.strip():
            continue
        if is_timestamp_line(line):
            if current_record:
                records.append(current_record)
            current_record = [line]
        elif current_record:
            current_record.append(line)
    if current_record:
        records.append(current_record)

    parsed: list[list[str]] = []
    for raw_record in records:
        record = rebuild_record(raw_record)
        if record:
            parsed.append(record)
    return parsed


def login() -> bool:
    if not USERNAME or not PASSWORD:
        raise RuntimeError("TEMP_NUMBERS_USERNAME and TEMP_NUMBERS_PASSWORD are required")

    response = session.get(
        f"{BASE_URL}/login",
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    captcha_match = re.search(r"What is (\d+) \+ (\d+) = ?", response.text)
    if not captcha_match:
        return False

    answer = int(captcha_match.group(1)) + int(captcha_match.group(2))
    login_response = session.post(
        f"{BASE_URL}/signin",
        data={"username": USERNAME, "password": PASSWORD, "capt": answer, "remember-me": "on"},
        headers={"User-Agent": USER_AGENT, "Referer": f"{BASE_URL}/login"},
        allow_redirects=True,
        timeout=REQUEST_TIMEOUT,
    )
    return login_response.ok and "x12" in session.cookies


def session_is_valid() -> bool:
    if "x12" not in session.cookies:
        return False
    response = session.get(
        f"{BASE_URL}/agent/SMSCDRReports",
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )
    return (
        response.status_code == 200
        and "/login" not in response.url.lower()
        and not ("signin" in response.text.lower() and "username" in response.text.lower())
    )


def ensure_login() -> bool:
    if session_is_valid():
        return True
    session.cookies.clear()
    for attempt in range(3):
        try:
            if login():
                return True
        except requests.RequestException:
            pass
        if attempt < 2:
            time.sleep(1)
    return False


def fetch_sms() -> str | None:
    with session_lock:
        if not ensure_login():
            return None
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        payload = {
            "fdate1": start_date, "fdate2": end_date, "frange": "",
            "fclient": "", "fnum": "", "fcli": "",
        }
        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{BASE_URL}/agent/SMSCDRReports",
            "User-Agent": USER_AGENT,
        }
        response = session.post(
            f"{BASE_URL}/agent/res/exportsmscdr",
            data=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code in (401, 403) or "/login" in response.url.lower():
            session.cookies.clear()
            if not login():
                return None
            response = session.post(
                f"{BASE_URL}/agent/res/exportsmscdr",
                data=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
        text = response.text.strip()
        if response.ok and text and "<html" not in text.lower() and "<!doctype" not in text.lower():
            return text
        return None


def poll_once() -> list[list[str]]:
    global latest_records, last_poll_at, last_error
    try:
        data = fetch_sms()
        if data is None:
            raise RuntimeError("Unable to authenticate or fetch SMS data")
        records = process_sms(data)
        new_records: list[list[str]] = []
        for record in records:
            key = tuple(record)
            if key not in seen_sms:
                seen_sms.add(key)
                new_records.append(record)
        latest_records = records
        last_error = None
        last_poll_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        return new_records
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        last_error = str(exc)
        last_poll_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        return []


def background_poller() -> None:
    while True:
        poll_once()
        time.sleep(POLL_INTERVAL)


def start_background_poller() -> None:
    global poller_started
    if os.getenv("ENABLE_POLLER", "false").lower() not in {"1", "true", "yes"} or poller_started:
        return
    poller_started = True
    threading.Thread(target=background_poller, name="sms-poller", daemon=True).start()


@app.get("/")
def index():
    return jsonify({"service": "sms-api", "status": "ok", "endpoints": ["/health", "/sms", "/poll"]})


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "poller_enabled": os.getenv("ENABLE_POLLER", "false").lower() in {"1", "true", "yes"},
        "last_poll_at": last_poll_at,
        "last_error": last_error,
    })


@app.get("/sms")
def sms():
    fresh = request.args.get("fresh", "false").lower() in {"1", "true", "yes"}
    if fresh:
        poll_once()
    return jsonify({"columns": OUTPUT_HEADER, "records": latest_records, "count": len(latest_records), "last_poll_at": last_poll_at})


@app.post("/poll")
def poll():
    records = poll_once()
    if last_error:
        return jsonify({"error": last_error, "records": [], "count": 0}), 502
    return jsonify({"columns": OUTPUT_HEADER, "records": records, "count": len(records), "last_poll_at": last_poll_at})


start_background_poller()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
