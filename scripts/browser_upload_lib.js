const fs = require('fs');
const { chromium } = require('playwright-core');

function detectBrowserExecutable() {
  const envPath = process.env.CHROME_PATH;
  if (envPath && fs.existsSync(envPath)) return envPath;

  const candidates = [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/microsoft-edge',
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

function toPlaywrightCookies(cookies) {
  return Object.entries(cookies).map(([name, value]) => ({
    name,
    value,
    domain: '.bing.com',
    path: '/',
    httpOnly: false,
    secure: true,
    sameSite: 'None',
  }));
}

function guessMimeType(filePath) {
  const lower = String(filePath || '').toLowerCase();
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg';
  if (lower.endsWith('.webp')) return 'image/webp';
  return 'image/png';
}

function ok(payload) {
  return { ok: true, ...payload };
}

function fail(stage, code, message, extra = {}) {
  return { ok: false, stage, code, message, ...extra };
}

async function launchBrowser(proxyServer = '') {
  const executablePath = detectBrowserExecutable();
  if (!executablePath) {
    return { ok: false, error: fail('bootstrap', 'browser_not_found', 'No Chrome/Edge executable found. Set CHROME_PATH.') };
  }
  try {
    const browser = await chromium.launch({
      executablePath,
      headless: true,
      proxy: proxyServer ? { server: proxyServer } : undefined,
    });
    return { ok: true, browser, executablePath };
  } catch (err) {
    return { ok: false, error: fail('browser', 'browser_launch_failed', String(err)) };
  }
}

async function uploadWithBrowser(browser, executablePath, { cookies, imagePath }) {
  if (!imagePath || !fs.existsSync(imagePath)) {
    return fail('bootstrap', 'image_file_missing', 'Image file is missing');
  }
  const imageBase64 = fs.readFileSync(imagePath).toString('base64');
  const imageMimeType = guessMimeType(imagePath);
  const startedAt = Date.now();

  const context = await browser.newContext();
  try {
    await context.addCookies(toPlaywrightCookies(cookies));
    const page = await context.newPage();
    try {
      await page.goto('https://www.bing.com/images/create?FORM=GENEXP&ctype=video', { waitUntil: 'domcontentloaded', timeout: 30000 });
    } catch (err) {
      return fail('prepare', 'create_page_open_failed', String(err), { browser_executable: executablePath });
    }

    const sidWaitStartedAt = Date.now();
    let sid = null;
    while (Date.now() - sidWaitStartedAt < 3000) {
      const jar = await page.context().cookies('https://www.bing.com');
      const ssCookie = jar.find((c) => c.name === '_SS');
      const sidMatch = ssCookie && ssCookie.value.match(/SID=([^&;]+)/);
      sid = sidMatch ? sidMatch[1] : null;
      if (sid) break;
      await page.waitForTimeout(200);
    }
    if (!sid) {
      return fail('prepare', 'sid_missing', 'No SID found in _SS cookie');
    }

    const result = await page.evaluate(async ({ sid, imageBase64, imageMimeType }) => {
      async function toUploadJpegBase64(sourceBase64, sourceMimeType) {
        const img = new Image();
        const dataUrl = `data:${sourceMimeType};base64,${sourceBase64}`;
        await new Promise((resolve, reject) => {
          img.onload = resolve;
          img.onerror = reject;
          img.src = dataUrl;
        });

        let { width, height } = img;
        if (sourceMimeType === 'image/jpeg') {
          return { quality: 'original', width, height, chars: sourceBase64.length, jpegBase64: sourceBase64 };
        }

        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, width, height);

        const qualities = [0.88, 0.80, 0.72, 0.64, 0.56];
        let last = null;
        for (const q of qualities) {
          const jpegUrl = canvas.toDataURL('image/jpeg', q);
          const jpegBase64 = jpegUrl.split(',')[1];
          last = { quality: q, width, height, chars: jpegBase64.length, jpegBase64 };
          if (jpegBase64.length <= 160000) {
            return last;
          }
        }
        return last;
      }

      const convertStartedAt = performance.now();
      const converted = await toUploadJpegBase64(imageBase64, imageMimeType);
      const convertMs = Math.round(performance.now() - convertStartedAt);
      const form = new FormData();
      form.append('imageBase64', converted.jpegBase64);
      const uploadStartedAt = performance.now();
      const resp = await fetch(`/images/create/upload?&sid=${sid}`, {
        method: 'POST',
        body: form,
        credentials: 'include',
        headers: { accept: '*/*' },
      });
      const text = await resp.text();
      const uploadMs = Math.round(performance.now() - uploadStartedAt);
      return {
        status: resp.status,
        text,
        converted: {
          quality: converted.quality,
          width: converted.width,
          height: converted.height,
          chars: converted.chars,
          prefix: converted.jpegBase64.slice(0, 20),
        },
        timings: {
          convert_ms: convertMs,
          upload_ms: uploadMs,
        },
      };
    }, { sid, imageBase64, imageMimeType });

    if (result.status !== 200) {
      return fail('upload', `upload_http_${result.status}`, 'Bing upload returned non-200', {
        status: result.status,
        text: result.text || '',
        sid,
        converted: result.converted,
        timings: {
          page_open_and_sid_ms: Date.now() - startedAt,
          sid_wait_ms: Date.now() - sidWaitStartedAt,
          convert_ms: result.timings ? result.timings.convert_ms : null,
          upload_ms: result.timings ? result.timings.upload_ms : null,
          total_ms: Date.now() - startedAt,
        },
      });
    }

    let data = null;
    try {
      data = JSON.parse(result.text || '{}');
    } catch (err) {
      return fail('upload', 'upload_invalid_json', 'Upload returned non-JSON body', {
        status: result.status,
        text: result.text || '',
        sid,
        converted: result.converted,
      });
    }

    if (!data || !data.bcid) {
      return fail('upload', 'upload_no_bcid', 'Upload succeeded but no bcid was returned', {
        status: result.status,
        text: result.text || '',
        sid,
        converted: result.converted,
      });
    }

    return ok({
      stage: 'upload',
      status: result.status,
      sid,
      bcid: data.bcid,
      converted: result.converted,
      timings: {
        page_open_and_sid_ms: Date.now() - startedAt,
        sid_wait_ms: Date.now() - sidWaitStartedAt,
        convert_ms: result.timings ? result.timings.convert_ms : null,
        upload_ms: result.timings ? result.timings.upload_ms : null,
        total_ms: Date.now() - startedAt,
      },
      browser_executable: executablePath,
    });
  } finally {
    await context.close();
  }
}

module.exports = {
  detectBrowserExecutable,
  launchBrowser,
  uploadWithBrowser,
};
