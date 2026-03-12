from typing import Dict, List

from bing_api.clients.video import AsyncBingVideoClient
from bing_api.services.account_service import AccountService


class DurationProbeService:
    def __init__(self, account_service: AccountService) -> None:
        self.account_service = account_service

    async def probe_hidden_duration(self, account_id: str, prompt: str, ar: str = "1") -> List[Dict[str, str]]:
        record = await self.account_service.get_record(account_id)
        variants = [
            ("baseline", {}, {}),
            ("form_duration", {}, {"duration": "12"}),
            ("form_duration_s", {}, {"duration_s": "12"}),
            ("form_seconds", {}, {"seconds": "12"}),
            ("form_videoLength", {}, {"videoLength": "12"}),
            ("query_duration", {"duration": "12"}, {}),
            ("query_duration_s", {"duration_s": "12"}, {}),
            ("query_seconds", {"seconds": "12"}, {}),
            ("query_videoLength", {"videoLength": "12"}, {}),
            ("query_n_frames", {"n_frames": "360"}, {}),
            ("form_n_frames", {}, {"n_frames": "360"}),
        ]
        results: List[Dict[str, str]] = []
        async with AsyncBingVideoClient(record.cookies) as client:
            for name, qextra, fextra in variants:
                response = await client.post(
                    "/images/create/ai-video-generator",
                    params={
                        "q": prompt,
                        "rt": "4",
                        "mdl": "0",
                        "ar": ar,
                        "FORM": "GENCRE",
                        "sm": "1",
                        **qextra,
                    },
                    data={
                        "q": prompt,
                        "model": "gpt4o",
                        "aspectRatio": "9:16" if ar == "1" else "16:9",
                        **fextra,
                    },
                )
                results.append(
                    {
                        "variant": name,
                        "status_code": str(response.status_code),
                        "location": response.headers.get("location", ""),
                        "body_preview": response.text[:200],
                    }
                )
        return results
