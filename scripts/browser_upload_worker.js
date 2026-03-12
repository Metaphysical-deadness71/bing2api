const readline = require('readline');
const { launchBrowser, uploadWithBrowser } = require('./browser_upload_lib');

let browser = null;
let executablePath = null;

async function ensureBrowser() {
  if (browser) return { ok: true, browser, executablePath };
  const proxyServer = process.env.BROWSER_PROXY || process.env.HTTPS_PROXY || process.env.HTTP_PROXY || '';
  const launched = await launchBrowser(proxyServer);
  if (!launched.ok) return launched;
  browser = launched.browser;
  executablePath = launched.executablePath;
  return { ok: true, browser, executablePath };
}

async function handleCommand(line) {
  let payload;
  try {
    payload = JSON.parse(line);
  } catch (err) {
    process.stdout.write(JSON.stringify({ ok: false, stage: 'worker', code: 'invalid_command_json', message: String(err) }) + '\n');
    return;
  }

  if (payload.type === 'health') {
    const launched = await ensureBrowser();
    process.stdout.write(JSON.stringify(launched.ok ? { ok: true, browser_executable: launched.executablePath } : launched.error) + '\n');
    return;
  }

  if (payload.type !== 'upload') {
    process.stdout.write(JSON.stringify({ ok: false, stage: 'worker', code: 'unknown_command', message: 'Unknown command' }) + '\n');
    return;
  }

  const launched = await ensureBrowser();
  if (!launched.ok) {
    process.stdout.write(JSON.stringify(launched.error) + '\n');
    return;
  }

  try {
    const result = await uploadWithBrowser(browser, executablePath, {
      cookies: payload.cookies || {},
      imagePath: payload.imagePath,
    });
    process.stdout.write(JSON.stringify(result) + '\n');
  } catch (err) {
    process.stdout.write(JSON.stringify({ ok: false, stage: 'worker', code: 'upload_failed', message: String(err) }) + '\n');
  }
}

const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
rl.on('line', (line) => {
  handleCommand(line);
});

async function shutdown() {
  if (browser) {
    try { await browser.close(); } catch (_) {}
  }
  process.exit(0);
}

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
