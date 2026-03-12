import argparse
import asyncio
import json
from http.cookies import SimpleCookie

from bing_api.clients.base import AsyncBingBaseClient
from bing_api.clients.video import AsyncBingVideoClient


def parse_cookie_header(raw: str) -> dict[str, str]:
    cookie = SimpleCookie()
    cookie.load(raw)
    return {key: morsel.value for key, morsel in cookie.items()}


def load_cookie_header(args: argparse.Namespace) -> str:
    if args.cookie_header:
        return args.cookie_header.strip()
    if args.cookie_header_file:
        with open(args.cookie_header_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    raise SystemExit("Provide --cookie-header or --cookie-header-file")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe whether a Bing cookie session is usable for video generation.")
    parser.add_argument("--cookie-header", help="Raw Bing Cookie header")
    parser.add_argument("--cookie-header-file", help="File containing raw Bing Cookie header")
    parser.add_argument("--prompt", default="a cat", help="Prompt to use for create probe")
    parser.add_argument("--ar", default="1", help="Bing ar value: 1=portrait, 5=landscape")
    parser.add_argument("--aspect-ratio", default="9:16", help="Aspect ratio form value")
    parser.add_argument("--probe-create", action="store_true", help="Attempt a real create request")
    return parser


async def main_async(args: argparse.Namespace) -> None:
    cookie_header = load_cookie_header(args)
    cookies = parse_cookie_header(cookie_header)

    result: dict[str, object] = {
        "input_cookie_names": sorted(cookies.keys()),
    }

    async with AsyncBingBaseClient(cookies) as base_client:
        home = await base_client.get("/")
        video = await base_client.get("/images/create?ctype=video&FORM=GENEXP")
        ai_video = await base_client.get("/images/create/ai-video-generator?FORM=GENEXP")
        exported = base_client.export_cookies()

        result["page_checks"] = {
            "home_status": home.status_code,
            "home_url": str(home.url),
            "video_status": video.status_code,
            "video_url": str(video.url),
            "ai_video_status": ai_video.status_code,
            "ai_video_url": str(ai_video.url),
        }
        result["refreshed_cookie_names"] = sorted(exported.keys())
        result["has__U"] = "_U" in exported
        result["has__EDGE_S"] = "_EDGE_S" in exported
        result["sid"] = await base_client.get_sid()

    if args.probe_create:
        async with AsyncBingVideoClient(cookies) as video_client:
            created = await video_client.create_video_generation(
                prompt=args.prompt,
                aspect_ratio=args.aspect_ratio,
                ar=args.ar,
                model="gpt4o",
                extra_query={"mdl": "0"},
            )
            result["create_probe"] = {
                "job_id": created.job_id,
                "poll_path": created.poll_path,
                "response_url": created.response_url,
            }

    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
