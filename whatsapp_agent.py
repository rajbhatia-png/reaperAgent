#!/usr/bin/env python3
"""WhatsApp instruction agent.

Reads a .txt/.md instruction file and sends messages to one WhatsApp number.
Uses WhatsApp Cloud API (Meta Graph API).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union


@dataclass
class SendStep:
    text: str


@dataclass
class WaitStep:
    seconds: float


Step = Union[SendStep, WaitStep]


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def normalize_phone_number(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if not (8 <= len(digits) <= 15):
        raise ValueError(
            "Invalid phone number format. Use country code + number, e.g. +14155552671"
        )
    return digits


def markdown_line_to_text(line: str) -> str:
    line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
    line = re.sub(r"^\s*[-*+]\s+", "", line)
    line = re.sub(r"^\s*\d+\.\s+", "", line)
    line = re.sub(r"^\s*>\s*", "", line)
    return line.strip()


def parse_steps(text: str, extension: str) -> List[Step]:
    steps: List[Step] = []
    lines = text.splitlines()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        wait_match = re.match(r"^WAIT:\s*([0-9]+(?:\.[0-9]+)?)\s*$", stripped, re.I)
        if wait_match:
            steps.append(WaitStep(float(wait_match.group(1))))
            continue
        send_match = re.match(r"^SEND:\s*(.+)\s*$", stripped, re.I)
        if send_match:
            steps.append(SendStep(send_match.group(1).strip()))

    if steps:
        return steps

    # No explicit SEND/WAIT directives. Fall back to paragraphs.
    normalized_lines: List[str] = []
    for line in lines:
        if extension == ".md":
            normalized_lines.append(markdown_line_to_text(line))
        else:
            normalized_lines.append(line.strip())
    normalized_text = "\n".join(normalized_lines)
    blocks = [block.strip() for block in re.split(r"\n\s*\n", normalized_text) if block.strip()]

    for block in blocks:
        cleaned = re.sub(r"\n+", " ", block).strip()
        if cleaned:
            steps.append(SendStep(cleaned))
    return steps


def send_whatsapp_text(
    *,
    token: str,
    phone_number_id: str,
    recipient_number: str,
    message: str,
    api_version: str,
    timeout_seconds: int,
) -> dict:
    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient_number,
        "type": "text",
        "text": {"preview_url": False, "body": message},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"WhatsApp API request failed with HTTP {exc.code}. Response: {body}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error while calling WhatsApp API: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read instruction file (.txt/.md) and send message steps to one WhatsApp number."
        )
    )
    parser.add_argument(
        "--instructions",
        required=True,
        help="Path to .txt or .md instructions file.",
    )
    parser.add_argument(
        "--to",
        required=True,
        help="Recipient phone number with country code, e.g. +14155552671.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=1.0,
        help="Delay after each SEND step when file does not include WAIT directives.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="HTTP timeout for each API request.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print steps instead of sending WhatsApp messages.",
    )
    parser.add_argument(
        "--dotenv",
        default=".env",
        help="Path to .env file for WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    instructions_path = Path(args.instructions)
    if not instructions_path.exists():
        print(f"Instruction file not found: {instructions_path}", file=sys.stderr)
        return 1

    if instructions_path.suffix.lower() not in {".txt", ".md"}:
        print("Only .txt and .md instruction files are supported.", file=sys.stderr)
        return 1

    load_dotenv(Path(args.dotenv))

    token = os.environ.get("WHATSAPP_TOKEN", "").strip()
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    api_version = os.environ.get("WHATSAPP_API_VERSION", "v21.0").strip()

    if not args.dry_run:
        if not token:
            print("Missing WHATSAPP_TOKEN.", file=sys.stderr)
            return 1
        if not phone_number_id:
            print("Missing WHATSAPP_PHONE_NUMBER_ID.", file=sys.stderr)
            return 1

    try:
        recipient_number = normalize_phone_number(args.to)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    source = instructions_path.read_text(encoding="utf-8")
    steps = parse_steps(source, instructions_path.suffix.lower())
    if not steps:
        print("No actionable steps found in instruction file.", file=sys.stderr)
        return 1

    has_explicit_waits = any(isinstance(s, WaitStep) for s in steps)

    sent_count = 0
    for step in steps:
        if isinstance(step, WaitStep):
            print(f"[WAIT] {step.seconds}s")
            if not args.dry_run:
                time.sleep(step.seconds)
            continue

        message = step.text
        print(f"[SEND] {message}")
        if args.dry_run:
            sent_count += 1
            continue

        response = send_whatsapp_text(
            token=token,
            phone_number_id=phone_number_id,
            recipient_number=recipient_number,
            message=message,
            api_version=api_version,
            timeout_seconds=args.timeout_seconds,
        )
        sent_count += 1
        print(f"[OK] API response: {json.dumps(response)}")

        if not has_explicit_waits and args.delay_seconds > 0:
            time.sleep(args.delay_seconds)

    print(f"Done. Sent messages: {sent_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
