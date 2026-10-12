import { chromium } from "playwright-core";
import fs from "node:fs";

fs.mkdirSync("screenshots/light", { recursive: true });
const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "light" });
const page = await ctx.newPage();

await page.goto("http://localhost:5173/login");
await page.getByLabel("Employee ID").fill("ADMIN001");
await page.getByLabel("Password").fill("Pass@123");
await page.getByRole("button", { name: "Sign in" }).click();
await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 10000 });

await page.goto("http://localhost:5173/account");
await page.waitForTimeout(600);
const isDark = await page.evaluate(() => document.documentElement.classList.contains("dark"));
if (isDark) {
  await page.click('button[role="switch"]');
  await page.waitForTimeout(600);
}

const PAGES = [
  ["dashboard", "/"],
  ["orders-mark", "/orders"],
  ["orders-overview", "/orders/overview"],
  ["tickets", "/tickets"],
  ["stores", "/stores"],
  ["billing", "/accounts"],
  ["attendance", "/attendance"],
  ["reports", "/reports"],
  ["account", "/account"],
];

for (const [name, path] of PAGES) {
  await page.goto("http://localhost:5173" + path);
  await page.waitForTimeout(600);
  await page.screenshot({ path: `screenshots/light/${name}.png` });
  console.log("Captured light:", name);
}

await browser.close();
console.log("Done capturing light screenshots!");
