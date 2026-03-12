const fs = require('fs');
const { launchBrowser, uploadWithBrowser, fail } = (() => {
  const lib = require('./browser_upload_lib');
  return {
    launchBrowser: lib.launchBrowser,
    uploadWithBrowser: lib.uploadWithBrowser,
    fail: (stage, code, message, extra = {}) => {
      process.stdout.write(JSON.stringify({ ok: false, stage, code, message, ...extra }));
      process.exit(1);
    },
  };
})();

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith('--')) continue;
    args[token.slice(2)] = argv[i + 1];
    i += 1;
  }
  return args;
}

async function main() {
  const args = parseArgs(process.argv);
  const cookiePath = args.cookies;
  const imagePath = args.image;
  if (!cookiePath || !fs.existsSync(cookiePath)) {
    fail('bootstrap', 'cookie_file_missing', 'Cookie JSON file is missing');
  }
  if (!imagePath || !fs.existsSync(imagePath)) {
    fail('bootstrap', 'image_file_missing', 'Image file is missing');
  }

  const cookies = JSON.parse(fs.readFileSync(cookiePath, 'utf-8'));
  const proxyServer = process.env.BROWSER_PROXY || process.env.HTTPS_PROXY || process.env.HTTP_PROXY || '';
  const launched = await launchBrowser(proxyServer);
  if (!launched.ok) {
    process.stdout.write(JSON.stringify(launched.error));
    process.exit(1);
  }
  const { browser, executablePath } = launched;
  try {
    const result = await uploadWithBrowser(browser, executablePath, { cookies, imagePath });
    process.stdout.write(JSON.stringify(result));
    process.exit(result.ok ? 0 : 1);
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  fail('unknown', 'unexpected_error', String(err));
});
