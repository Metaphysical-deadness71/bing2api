import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ProbeRecord:
    email: str
    password: str
    client_id: str
    refresh_token: str


def parse_record(line: str) -> ProbeRecord:
    email, password, client_id, refresh_token = line.strip().split("----", 3)
    return ProbeRecord(
        email=email,
        password=password,
        client_id=client_id,
        refresh_token=refresh_token,
    )


def load_record(file_path: str, index: int) -> ProbeRecord:
    lines = [line for line in Path(file_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if index < 0 or index >= len(lines):
        raise SystemExit(f"index {index} out of range, total lines={len(lines)}")
    return parse_record(lines[index])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Local Path B probe scaffold. This script does NOT perform the protected login flow for you. "
            "It helps you inspect one Outlook material record and record your manual probe results in a structured way."
        )
    )
    parser.add_argument("--file", default="/mnt/e/bing2api/outlook.txt", help="Path to outlook material file")
    parser.add_argument("--index", type=int, default=0, help="0-based line index to inspect")
    parser.add_argument("--output", default="/mnt/e/bing2api/path_b_probe_result.json", help="Where to save the probe template/result")
    parser.add_argument("--bing-cookie-header", default="", help="Optional Bing cookie header you manually obtained after testing")
    parser.add_argument("--note", default="", help="Optional note about what happened during your manual test")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    record = load_record(args.file, args.index)

    output = {
        "selected_record": {
            "email": record.email,
            "password_present": bool(record.password),
            "client_id": record.client_id,
            "refresh_token_prefix": record.refresh_token[:24],
            "refresh_token_length": len(record.refresh_token),
        },
        "manual_probe_plan": {
            "step_1": "Use your own local code or existing workflow to verify this refresh token can obtain a fresh Microsoft token.",
            "step_2": "Use the refreshed Microsoft login state to open bing.com and bing video creator in your own environment.",
            "step_3": "If Bing session appears logged in, capture the resulting Bing Cookie header or at least _U/_EDGE_S.",
            "success_signal": "Bing cookie header contains _U, ideally also _EDGE_S.",
        },
        "manual_results": {
            "bing_cookie_header": args.bing_cookie_header,
            "note": args.note,
        },
    }

    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
