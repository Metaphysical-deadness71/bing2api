# bing2api

[简体中文](README.zh-CN.md) | [English](README.md)

<div align="center">

**OpenAI-compatible video API for Bing Video Creator**

</div>

---

## ✨ Features

### Core capabilities
- 🎬 **Text-to-video** - Generate videos from text prompts
- 🖼️ **Image-to-video** - Generate videos from uploaded images
- 🧭 **Fast/slow modes** - Explicit model IDs for speed control
- 🔄 **Async jobs** - Stable polling and result delivery
- 🎯 **OpenAI compatible** - `/v1/videos/generations` and `/v1/models`

### Production-ready features
- 👥 **Account pool routing** - Multi-account concurrency and failover
- 🧪 **Quota detection** - Fast mode quota recognition
- 📦 **SQLite persistence** - Account and job storage
- 🧰 **Admin UI** - Account import and session maintenance
 - ⚙️ **Runtime settings** - Update API keys and proxy without restart

---

## 🚀 Quickstart

### Requirements
- Python 3.8+
- Valid Bing account cookies

### Local run
```bash
git clone git@github.com:jiwgxo/bing2api.git
cd bing2api
pip install -r requirements.txt
PYTHONPATH=src python -m bing_api.api.app
```

Open admin page: `http://localhost:8000/manage`

Default admin credentials:
- username: `admin`
- password: `admin123`

### Docker (recommended)
```bash
git clone git@github.com:jiwgxo/bing2api.git
cd bing2api
docker compose up -d --build
```

Open admin page: `http://localhost:8000/manage`

Default admin credentials:
- username: `admin`
- password: `admin123`

---

## 🔌 OpenAI-compatible API

### List models
```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer bing-demo-key"
```

### Generate video (portrait fast)
```bash
curl http://localhost:8000/v1/videos/generations \
  -H "Authorization: Bearer bing-demo-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sora-v2-portrait-fast",
    "prompt": "a cat",
    "async": true
  }'
```

### Generate video (landscape slow)
```bash
curl http://localhost:8000/v1/videos/generations \
  -H "Authorization: Bearer bing-demo-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sora-v2-landscape-slow",
    "prompt": "a cinematic cloudscape over the ocean",
    "async": true
  }'
```

### Query job result
```bash
curl http://localhost:8000/v1/videos/generations/<job_id> \
  -H "Authorization: Bearer bing-demo-key"
```

### Streaming behavior

The current Bing video API does **not** provide SSE / chunked streaming output and does not return `text/event-stream`.

This project therefore exposes the same stable task-based contract:

- `POST /v1/videos/generations`: submit a job
- `GET /v1/videos/generations/<job_id>`: poll job status and fetch the final result

Recommended client flow:

1. send `"async": true` when creating the job
2. read the `id` from the response
3. poll `/v1/videos/generations/<job_id>` periodically
4. read the result video URL once `status` becomes `succeeded`

Example:

```bash
curl http://localhost:8000/v1/videos/generations \
  -H "Authorization: Bearer bing-demo-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "sora-v2-fast",
    "prompt": "a panda riding a bicycle in the rain",
    "async": true
  }'
```

Typical response:

```json
{
  "id": "job_xxx",
  "object": "video.generation",
  "created": 1740000000,
  "model": "sora-v2-fast",
  "status": "queued"
}
```

Then poll:

```bash
curl http://localhost:8000/v1/videos/generations/job_xxx \
  -H "Authorization: Bearer bing-demo-key"
```

Completed response example:

```json
{
  "id": "job_xxx",
  "object": "video.generation",
  "created": 1740000000,
  "model": "sora-v2-fast",
  "status": "succeeded",
  "result": {
    "url": "https://...mp4",
    "thumbnail_url": "https://...jpg",
    "mime_type": "video/mp4",
    "aspect_ratio": "16:9"
  }
}
```

If you send `"async": false`, the server waits and returns one final JSON response after completion. That is still a blocking single response, not a streaming response.

This project also provides a video generation frontend: `test-video.html`

---

## ✅ Validated scope
- Text-to-video: end-to-end verified
- Image-to-video: end-to-end verified
- Explicit fast/slow models: verified
- Fast quota detection: verified
- Account pool routing and concurrency: production-ready baseline

---

## ⚠️ Limitations
- Requires valid Bing account cookies and active session state
- `skey` is short-lived and fetched per card/detail flow
- Output videos may include a static watermark (not removed)
- 12s duration is experimental; outputs still render 8s

---

## 🔐 Get Bing cookies

### Chromium-based browsers (Edge/Brave/Opera)
- Open https://bing.com/
- Press F12 → Console
- Run:
  ```js
  cookieStore.get("_U").then(result => console.log(result.value))
  ```
- Copy `_U` for import

### Recommended Bing session extraction script
If `_EDGE_S` is not shown in the console but appears in Application/Cookies, use visible cookies as an initial session and let the backend refresh Bing session state. You can extract manually from a logged-in page using:

```js
Promise.all([
  "_U",
  "_EDGE_S",
  "SRCHUSR",
  "SRCHUID",
  "SRCHD",
  "MUID",
  "MUIDB",
  "ANON",
  "WLS"
].map(name => cookieStore.get(name).then(v => [name, v?.value || null])))
  .then(entries => entries.filter(([, v]) => v))
  .then(entries => entries.map(([k, v]) => `${k}=${v}`).join("; "))
  .then(console.log)
```

**Full cookie set (required for image-to-video)**

Image-to-video upload requires `.MSA.Auth` (a httpOnly cookie that cannot be read by JavaScript). To extract it:

1. Open https://www.bing.com/images/create/ai-video-generator in a logged-in browser
2. Press F12 → Network tab
3. Reload the page
4. Click on the first request to `bing.com`
5. In the Headers tab, find the `cookie:` request header
6. Copy the **entire** cookie header value and paste it when importing the account

The admin import field accepts a full cookie header string and will parse all key-value pairs automatically.

Image-to-video upload currently uses **real browser automation** so the upload request runs inside an actual browser session. Before using image-to-video, make sure the environment has:

- Node.js
- `playwright-core` (already declared in `package.json`)
- A local Chrome / Edge executable
- A working proxy if your Bing access depends on one

You can override the browser path with `CHROME_PATH` and the browser proxy with `BROWSER_PROXY`.

**Minimal cookie set (text-to-video only)**
`_U + _EDGE_S + SRCHUSR + SRCHUID + SRCHD + MUID + MUIDB + ANON + WLS`

If the browser only exposes `_U` and a few session cookies, you can still import the partial cookie header and use the admin `Refresh session` action to warm Bing and auto-fill `_EDGE_S` when Bing issues it.

For multiple accounts, the admin UI supports batch session refresh to fill `_EDGE_S` and update fast-mode quotas.

Recommended workflow:
1. import lightweight Bing cookies
2. run batch account preparation
3. let the backend refresh Bing session and fill `_EDGE_S`
4. let the backend refresh fast-mode quota status
5. only then place accounts into routing

### Firefox
- Open https://bing.com/
- Press F12 to open developer tools
- Go to the Storage tab
- Expand Cookies
- Select `https://bing.com`
- Copy the `_U` value

---

## 🧭 Routing and concurrency guidance
- Text-to-video: use lightweight `_U` sessions
- Image-to-video: requires the full cookie set including `.MSA.Auth`; copy the full cookie header from the browser Network panel
- Derive `SID` dynamically before each upload
- Account pool routing + per-account concurrency + failover

---

## ⚙️ Runtime settings
The admin console now includes a **Settings** tab. Changes are persisted to `data/settings.json` and applied immediately without restarting the service.

Supported updates:
- OpenAI API keys (comma-separated)
- Global proxy
- Poll interval / timeouts (fast/slow)
- Image-to-video upload mode (browser-first / browser-only)
- Image-to-video browser upload concurrency limit

---

## 🧰 Path B (experimental)
`Outlook refresh token -> Microsoft state -> Bing session -> _U/_EDGE_S`

Research only. Do not use for production until validated.

---

## Legacy image CLI
The legacy image generation CLI (`python3 -m BingImageCreator`) and its documentation are from the old BingImageCreator project and are not part of the bing2api video API workflow.

---

## 🎯 Supported models

| Model ID | Aspect | Mode | Notes |
| --- | --- | --- | --- |
| `sora-v2-fast` | 16:9 | fast | Text-to-video / image-to-video |
| `sora-v2-slow` | 16:9 | slow | Text-to-video / image-to-video |
| `sora-v2-landscape-fast` | 16:9 | fast | Text-to-video / image-to-video |
| `sora-v2-landscape-slow` | 16:9 | slow | Text-to-video / image-to-video |
| `sora-v2-portrait-fast` | 9:16 | fast | Text-to-video / image-to-video |
| `sora-v2-portrait-slow` | 9:16 | slow | Text-to-video / image-to-video |

---

## 📄 License
GPL-2.0. See [LICENSE](LICENSE).
