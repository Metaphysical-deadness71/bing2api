import argparse
import json
from pathlib import Path

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe whether an existing Microsoft login state yields Bing _U/_EDGE_S cookies.")
    parser.add_argument("--cookie-header-file", help="Path to a text file containing a Cookie header value.")
    parser.add_argument("--cookie-header", help="Raw Cookie header value.")
    parser.add_argument(
        "--urls",
        nargs="*",
        default=[
            "https://www.bing.com/",
            "https://www.bing.com/images/create?ctype=video&FORM=GENEXP",
        ],
        help="URLs to visit in order while checking whether Bing cookies appear.",
    )
    parser.add_argument("--output", help="Optional path to save JSON results.")
    return parser.parse_args()


def parse_cookie_header(raw: str) -> dict:
    cookies = {}
    for part in raw.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies[name.strip()] = value.strip()
    return cookies


def load_cookie_header(args: argparse.Namespace) -> str:
    if args.cookie_header:
        return args.cookie_header.strip()
    if args.cookie_header_file:
        return Path(args.cookie_header_file).read_text(encoding="utf-8").strip()
    raise SystemExit("You must provide --cookie-header or --cookie-header-file")


def main() -> None:
    args = parse_args()
    cookie_header = load_cookie_header(args)
    cookies = parse_cookie_header(cookie_header)

    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 Edg/145.0.0.0",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    results = {
        "visited": [],
        "bing_cookies": {},
    }

    with httpx.Client(headers=headers, cookies=cookies, timeout=120, follow_redirects=True, trust_env=True) as client:
        for url in args.urls:
            response = client.get(url)
            snapshot = {
                "requested_url": url,
                "final_url": str(response.url),
                "status_code": response.status_code,
                "has__U": client.cookies.get("_U") is not None,
                "has__EDGE_S": client.cookies.get("_EDGE_S") is not None,
                "title": None,
            }
            title_start = response.text.lower().find("<title>")
            title_end = response.text.lower().find("</title>")
            if title_start != -1 and title_end != -1 and title_end > title_start:
                snapshot["title"] = response.text[title_start + 7 : title_end].strip()
            results["visited"].append(snapshot)

        for key in ["_U", "_EDGE_S", "SRCHUSR", "SRCHUID", "SRCHD", "MUID", "MUIDB", "ANON", "WLS"]:
            value = client.cookies.get(key)
            if value is not None:
                results["bing_cookies"][key] = value

    text = json.dumps(results, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
