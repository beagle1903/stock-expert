import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, unlink, writeFile } from "node:fs/promises";
import path from "node:path";

const DEFAULTS = {
  url: "https://tr.investing.com/equities/turkey",
  minRows: 500,
  maxMoreClicks: 12,
  timeoutSeconds: 180,
};

const TABLES = [
  {
    filename: "fiyat.csv",
    tab: "Fiyat",
    headers: ["İsim", "Son", "Yüksek", "Düşük", "Fark", "Fark %", "Hac.", "Zaman"],
  },
  {
    filename: "performans.csv",
    tab: "Performans",
    headers: ["İsim", "Günlük", "Haftalık", "1 Aylık", "YTD", "1 Yıllık", "3 Yıllık"],
  },
  {
    filename: "teknik.csv",
    tab: "Teknik",
    headers: ["İsim", "Saatlik", "Günlük", "Haftalık", "Aylık"],
  },
  {
    filename: "temel.csv",
    tab: "Temel",
    headers: [
      "İsim",
      "Ortalama Hacim (3Ay)",
      "Piyasa değeri",
      "Gelir",
      "Fiyat / Kazanç Oranı",
      "Beta",
    ],
  },
];

function parseArgs(argv) {
  const result = {
    url: DEFAULTS.url,
    minRows: DEFAULTS.minRows,
    maxMoreClicks: DEFAULTS.maxMoreClicks,
    timeoutSeconds: DEFAULTS.timeoutSeconds,
    headless: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--headless") {
      result.headless = true;
      continue;
    }
    const key = argument.replace(/^--/, "").replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
    if (!argument.startsWith("--") || index + 1 >= argv.length) {
      throw new Error(`Invalid argument: ${argument}`);
    }
    result[key] = argv[index + 1];
    index += 1;
  }
  for (const key of ["minRows", "maxMoreClicks", "timeoutSeconds"]) {
    result[key] = Number.parseInt(result[key], 10);
    if (!Number.isInteger(result[key]) || result[key] < 1) {
      throw new Error(`${key} must be a positive integer`);
    }
  }
  if (!result.output || !result.profileDir) {
    throw new Error("--output and --profile-dir are required");
  }
  return result;
}

function browserCandidates(explicitPath) {
  const candidates = [];
  if (explicitPath) candidates.push(explicitPath);
  if (process.platform === "win32") {
    const programFiles = process.env.ProgramFiles || "C:\\Program Files";
    const programFilesX86 = process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)";
    const localAppData = process.env.LOCALAPPDATA || "";
    candidates.push(
      path.join(programFilesX86, "Microsoft", "Edge", "Application", "msedge.exe"),
      path.join(programFiles, "Microsoft", "Edge", "Application", "msedge.exe"),
      path.join(programFiles, "Google", "Chrome", "Application", "chrome.exe"),
      path.join(programFilesX86, "Google", "Chrome", "Application", "chrome.exe"),
      path.join(localAppData, "Google", "Chrome", "Application", "chrome.exe"),
    );
  } else if (process.platform === "darwin") {
    candidates.push(
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    );
  } else {
    candidates.push(
      "/usr/bin/google-chrome",
      "/usr/bin/google-chrome-stable",
      "/usr/bin/microsoft-edge",
      "/usr/bin/microsoft-edge-stable",
      "/usr/bin/chromium",
      "/usr/bin/chromium-browser",
    );
  }
  return candidates.filter(Boolean);
}

function findBrowser(explicitPath) {
  const browser = browserCandidates(explicitPath).find((candidate) => existsSync(candidate));
  if (!browser) {
    throw new Error("Microsoft Edge or Google Chrome was not found; pass its executable with --browser");
  }
  return browser;
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitForFile(filePath, child, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (existsSync(filePath)) return;
    if (child.exitCode !== null) {
      throw new Error(`Browser exited before its debugging session started (exit ${child.exitCode})`);
    }
    await delay(100);
  }
  throw new Error("Timed out while starting the browser");
}

class CdpClient {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.pending = new Map();
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (!message.id) return;
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      if (message.error) pending.reject(new Error(message.error.message));
      else pending.resolve(message.result);
    });
  }

  static async connect(url) {
    const socket = new WebSocket(url);
    await new Promise((resolve, reject) => {
      socket.addEventListener("open", resolve, { once: true });
      socket.addEventListener("error", () => reject(new Error("Could not connect to the browser")), {
        once: true,
      });
    });
    return new CdpClient(socket);
  }

  send(method, params = {}) {
    const id = this.nextId;
    this.nextId += 1;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    this.socket.close();
  }
}

async function evaluate(client, expression) {
  const response = await client.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails) {
    throw new Error(response.exceptionDetails.text || "Browser evaluation failed");
  }
  return response.result.value;
}

async function waitFor(client, expression, timeoutMs, description) {
  const deadline = Date.now() + timeoutMs;
  let lastValue;
  while (Date.now() < deadline) {
    lastValue = await evaluate(client, expression);
    if (lastValue) return lastValue;
    await delay(250);
  }
  throw new Error(`Timed out waiting for ${description}; last state=${JSON.stringify(lastValue)}`);
}

const PAGE_HELPERS = String.raw`
  const clean = (value) => (value || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  const normalize = (value) => clean(value)
    .replace(/[İı]/g, "I")
    .replace(/[Şş]/g, "S")
    .replace(/[Ğğ]/g, "G")
    .replace(/[Üü]/g, "U")
    .replace(/[Öö]/g, "O")
    .replace(/[Çç]/g, "C")
    .toUpperCase();
  const visible = (element) => Boolean(element && element.getClientRects().length);
  const stockTable = () => [...document.querySelectorAll("table")]
    .map((table) => ({ table, rows: table.querySelectorAll("tbody tr").length }))
    .filter(({ table }) => visible(table))
    .sort((left, right) => right.rows - left.rows)[0]?.table || null;
  const exactVisible = (selector, labels) => {
    const normalizedLabels = labels.map(normalize);
    return [...document.querySelectorAll(selector)].filter(
      (element) => visible(element) && normalizedLabels.includes(normalize(element.innerText || element.textContent))
    );
  };
`;

function pageExpression(body) {
  return `(() => { ${PAGE_HELPERS} ${body} })()`;
}

async function dismissBlockingNotice(client) {
  return evaluate(
    client,
    pageExpression(`
      const buttons = [...document.querySelectorAll("button")].filter(visible);
      const close = buttons.find((button) =>
        normalize(button.getAttribute("aria-label")) === "CLOSE" ||
        ["KAPAT", "CLOSE"].includes(normalize(button.innerText))
      );
      if (!close) return false;
      close.click();
      return true;
    `),
  );
}

async function waitForStockPage(client, timeoutMs, headless) {
  const deadline = Date.now() + timeoutMs;
  let challengeReported = false;
  while (Date.now() < deadline) {
    const state = await evaluate(
      client,
      pageExpression(`
        const title = normalize(document.title);
        const challenge = title.includes("JUST A MOMENT") ||
          title.includes("BIR DAKIKA") ||
          exactVisible("iframe, h1, h2, p", ["Verify you are human", "İnsan olduğunuzu doğrulayın"]).length > 0;
        return {
          ready: Boolean(stockTable() && stockTable().querySelectorAll("tbody tr").length),
          challenge,
          title: document.title,
        };
      `),
    );
    if (state.ready) return state;
    if (state.challenge && headless) {
      throw new Error("An access challenge appeared in headless mode; rerun without --headless");
    }
    if (state.challenge && !challengeReported) {
      process.stderr.write(
        "Investing.com requested a browser verification. Complete it in the opened browser window; waiting...\n",
      );
      challengeReported = true;
    }
    await delay(500);
  }
  throw new Error("The Investing.com stock table did not become available");
}

async function verifyCountry(client) {
  const countryState = await evaluate(
    client,
    pageExpression(`
      const inputs = [...document.querySelectorAll("input")];
      const country = inputs.map((input) => clean(input.parentElement?.innerText)).find(
        (text) => normalize(text) === "TURKIYE"
      );
      const heading = [...document.querySelectorAll("h1")].map((element) => clean(element.innerText)).find(
        (text) => normalize(text).includes("TURKIYE HISSELER")
      );
      return { country: country || null, heading: heading || null, url: location.href };
    `),
  );
  if (countryState.country) return countryState.country;
  if (countryState.heading && new URL(countryState.url).pathname === "/equities/turkey") {
    return "Türkiye";
  }
  if (!countryState.country) {
    throw new Error("Could not confirm the Türkiye country selection");
  }
  return countryState.country;
}

async function selectAllShares(client, timeoutMs) {
  const initialMarket = await waitFor(
    client,
    pageExpression(`
      const labels = ["Türkiye Tüm Hisse Senetleri", "Türkiye Tüm Hisseler"];
      const dropdowns = [...document.querySelectorAll("div")]
        .filter((element) => visible(element) && String(element.className).includes("dropdown_noSelect"))
        .map((element) => clean(element.innerText))
        .filter((text) => text.length < 100);
      return dropdowns.find((text) => labels.map(normalize).includes(normalize(text))) ||
        dropdowns.find((text) => normalize(text) === "BIST 100") ||
        null;
    `),
    Math.min(timeoutMs, 30_000),
    "the market selector to finish loading",
  );
  if (["TURKIYE TUM HISSE SENETLERI", "TURKIYE TUM HISSELER"].includes(
    initialMarket
      .replace(/[İı]/g, "I")
      .replace(/[Şş]/g, "S")
      .replace(/[Ğğ]/g, "G")
      .replace(/[Üü]/g, "U")
      .replace(/[Öö]/g, "O")
      .replace(/[Çç]/g, "C")
      .toUpperCase(),
  )) return initialMarket;

  const openState = await evaluate(
    client,
    pageExpression(`
      const matches = [...document.querySelectorAll("div")]
        .filter((element) => visible(element) && String(element.className).includes("dropdown_noSelect"))
        .filter((element) => normalize(element.innerText) === "BIST 100");
      const selected = matches.sort((left, right) => left.childElementCount - right.childElementCount)[0];
      if (!selected) {
        const candidates = [...document.querySelectorAll("div, button, span")]
          .map((element) => clean(element.innerText))
          .filter((text) => text.length < 100 && normalize(text).includes("BIST"))
          .slice(0, 12);
        return { opened: false, candidates };
      }
      selected.click();
      return { opened: true, candidates: [clean(selected.innerText)] };
    `),
  );
  if (!openState.opened) {
    throw new Error(`Could not open the BİST 100 market selector; visible labels=${JSON.stringify(openState.candidates)}`);
  }

  await delay(200);
  await dismissBlockingNotice(client);
  const selected = await waitFor(
    client,
    pageExpression(`
      const labels = ["Türkiye Tüm Hisse Senetleri", "Türkiye Tüm Hisseler"];
      const matches = exactVisible("button, [role=option], li, div, span", labels)
        .filter((element) => ![...element.children].some((child) => labels.map(normalize).includes(normalize(child.innerText))));
      const option = matches.sort((left, right) => left.childElementCount - right.childElementCount)[0];
      if (!option) return null;
      option.click();
      return clean(option.innerText);
    `),
    Math.min(timeoutMs, 20_000),
    "the Türkiye all-shares option",
  );

  await waitFor(
    client,
    pageExpression(`
      const labels = ["Türkiye Tüm Hisse Senetleri", "Türkiye Tüm Hisseler"];
      return [...document.querySelectorAll("div")]
        .filter((element) => visible(element) && String(element.className).includes("dropdown_noSelect"))
        .map((element) => clean(element.innerText))
        .find((text) => labels.map(normalize).includes(normalize(text))) || null;
    `),
    Math.min(timeoutMs, 30_000),
    "the all-shares market selection to refresh",
  );
  return selected;
}

async function selectTab(client, tabName, expectedHeaders, timeoutMs) {
  const clicked = await evaluate(
    client,
    pageExpression(`
      const tab = exactVisible('button[role="tab"], button[data-test="quote-tab"]', ${JSON.stringify([tabName])})[0];
      if (!tab) return false;
      if (tab.getAttribute("aria-selected") !== "true") tab.click();
      return true;
    `),
  );
  if (!clicked) throw new Error(`Could not find the ${tabName} tab`);

  const normalizedExpected = expectedHeaders.map((header) =>
    header
      .replace(/[İı]/g, "I")
      .replace(/[Şş]/g, "S")
      .replace(/[Ğğ]/g, "G")
      .replace(/[Üü]/g, "U")
      .replace(/[Öö]/g, "O")
      .replace(/[Çç]/g, "C")
      .replace(/[^A-Za-z0-9]/g, "")
      .toUpperCase(),
  );
  await waitFor(
    client,
    pageExpression(`
      const table = stockTable();
      if (!table) return false;
      const headers = [...table.querySelectorAll("thead th")]
        .map((cell) => normalize(cell.innerText).replace(/[^A-Z0-9]/g, ""))
        .filter(Boolean);
      return JSON.stringify(headers) === JSON.stringify(${JSON.stringify(normalizedExpected)});
    `),
    Math.min(timeoutMs, 30_000),
    `${tabName} table headers`,
  );
}

async function expandAllRows(client, maxClicks, timeoutMs) {
  let clicks = 0;
  for (; clicks < maxClicks; clicks += 1) {
    await evaluate(
      client,
      pageExpression(`
        const rows = stockTable()?.querySelectorAll("tbody tr") || [];
        rows[rows.length - 1]?.scrollIntoView({ block: "end" });
        window.scrollBy(0, Math.min(700, Math.max(300, window.innerHeight * 0.6)));
        return rows.length;
      `),
    );
    await delay(350);
    const state = await evaluate(
      client,
      pageExpression(`
        const table = stockTable();
        const button = [...document.querySelectorAll("button, [role=button], div, span, a")]
          .filter((element) => visible(element) && clean(element.innerText).length < 60)
          .filter((element) => normalize(element.innerText).includes("DAHA FAZLA"))
          .sort((left, right) => left.childElementCount - right.childElementCount)[0] || null;
        return { rows: table?.querySelectorAll("tbody tr").length || 0, hasMore: Boolean(button) };
      `),
    );
    if (!state.hasMore) return { clicks, rows: state.rows };

    const clicked = await evaluate(
      client,
      pageExpression(`
        const button = [...document.querySelectorAll("button, [role=button], div, span, a")]
          .filter((element) => visible(element) && clean(element.innerText).length < 60)
          .filter((element) => normalize(element.innerText).includes("DAHA FAZLA"))
          .sort((left, right) => left.childElementCount - right.childElementCount)[0] || null;
        if (!button) return false;
        button.scrollIntoView({ block: "center" });
        button.click();
        return true;
      `),
    );
    if (!clicked) throw new Error("The Daha Fazla button disappeared before it could be clicked");

    await waitFor(
      client,
      pageExpression(`
        const table = stockTable();
        const rows = table?.querySelectorAll("tbody tr").length || 0;
        const hasMore = [...document.querySelectorAll("button, [role=button], div, span, a")]
          .some((element) => visible(element) && clean(element.innerText).length < 60 &&
            normalize(element.innerText).includes("DAHA FAZLA"));
        return rows > ${state.rows} || !hasMore ? { rows, hasMore } : null;
      `),
      Math.min(timeoutMs, 20_000),
      "the stock table to add more rows",
    );
  }

  const stillVisible = await evaluate(
    client,
    pageExpression(`
      return [...document.querySelectorAll("button, [role=button], div, span, a")]
        .some((element) => visible(element) && clean(element.innerText).length < 60 &&
          normalize(element.innerText).includes("DAHA FAZLA"));
    `),
  );
  if (stillVisible) {
    throw new Error(`Daha Fazla is still visible after ${maxClicks} clicks`);
  }
  const rows = await evaluate(
    client,
    pageExpression(`return stockTable()?.querySelectorAll("tbody tr").length || 0;`),
  );
  return { clicks, rows };
}

async function extractTable(client, expectedColumnCount) {
  return evaluate(
    client,
    pageExpression(`
      const table = stockTable();
      if (!table) return null;
      const headers = [...table.querySelectorAll("thead th")]
        .map((cell) => clean(cell.innerText))
        .filter(Boolean);
      const rows = [...table.querySelectorAll("tbody tr")].map((row) => {
        const cells = [...row.querySelectorAll("td")].map((cell) => clean(cell.innerText));
        return cells.length > ${expectedColumnCount}
          ? cells.slice(cells.length - ${expectedColumnCount})
          : cells;
      });
      return { headers, rows };
    `),
  );
}

async function connectToPage(port) {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/list`);
      const targets = await response.json();
      const pageTarget = targets.find((target) => target.type === "page");
      if (pageTarget?.webSocketDebuggerUrl) {
        return CdpClient.connect(pageTarget.webSocketDebuggerUrl);
      }
    } catch {
      // The browser is still starting.
    }
    await delay(100);
  }
  throw new Error("Could not find the browser page target");
}

async function run() {
  const options = parseArgs(process.argv.slice(2));
  const browserPath = findBrowser(options.browser);
  const profileDir = path.resolve(options.profileDir);
  const outputPath = path.resolve(options.output);
  const activePortPath = path.join(profileDir, "DevToolsActivePort");
  await mkdir(profileDir, { recursive: true });
  await mkdir(path.dirname(outputPath), { recursive: true });
  await unlink(activePortPath).catch(() => {});

  const browserArgs = [
    "--remote-debugging-port=0",
    `--user-data-dir=${profileDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--new-window",
    "--window-size=1440,1000",
    "about:blank",
  ];
  if (options.headless) browserArgs.unshift("--headless=new", "--disable-gpu");

  const browser = spawn(browserPath, browserArgs, {
    stdio: ["ignore", "ignore", "ignore"],
    windowsHide: options.headless,
  });
  const timeoutMs = options.timeoutSeconds * 1000;
  let client;

  try {
    await waitForFile(activePortPath, browser, Math.min(timeoutMs, 15_000));
    const [portText] = (await readFile(activePortPath, "utf8")).split(/\r?\n/);
    const port = Number.parseInt(portText, 10);
    client = await connectToPage(port);
    await client.send("Page.enable");
    await client.send("Runtime.enable");
    await client.send("Page.navigate", { url: options.url });
    await waitForStockPage(client, timeoutMs, options.headless);
    await dismissBlockingNotice(client);

    const selectedCountry = await verifyCountry(client);
    const selectedMarket = await selectAllShares(client, timeoutMs);
    const tables = {};
    const moreClicks = {};

    for (const tableConfig of TABLES) {
      await selectTab(client, tableConfig.tab, tableConfig.headers, timeoutMs);
      const expanded = await expandAllRows(client, options.maxMoreClicks, timeoutMs);
      if (expanded.rows < options.minRows) {
        throw new Error(
          `${tableConfig.tab} stopped at ${expanded.rows} rows; expected at least ${options.minRows}`,
        );
      }
      const extracted = await extractTable(client, tableConfig.headers.length);
      if (!extracted) throw new Error(`Could not extract the ${tableConfig.tab} table`);
      tables[tableConfig.filename] = extracted;
      moreClicks[tableConfig.filename] = expanded.clicks;
    }

    await writeFile(
      outputPath,
      JSON.stringify(
        {
          source_url: options.url,
          selected_country: selectedCountry,
          selected_market: selectedMarket,
          extracted_at: new Date().toISOString(),
          more_clicks: moreClicks,
          tables,
        },
        null,
        2,
      ),
      "utf8",
    );
  } catch (error) {
    if (client) {
      const screenshot = await client.send("Page.captureScreenshot", { format: "png" }).catch(() => null);
      if (screenshot?.data) {
        await writeFile(`${outputPath}.failure.png`, Buffer.from(screenshot.data, "base64")).catch(() => {});
      }
    }
    throw new Error(error.message);
  } finally {
    if (client) {
      client.close();
    }
    if (browser.exitCode === null) browser.kill();
  }
}

run().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
});
