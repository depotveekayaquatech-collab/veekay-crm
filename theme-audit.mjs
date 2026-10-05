import { chromium } from "playwright-core";
import fs from "node:fs";

const OUT = process.env.AUDIT_OUT;
const BASE = "http://localhost:5173";
fs.mkdirSync(OUT, { recursive: true });

const PAGES = [
  ["dashboard", "/"], ["orders-mark", "/orders"], ["orders-overview", "/orders/overview"], ["orders-pending", "/orders/pending"],
  ["orders-correct", "/orders/correct"], ["tickets", "/tickets"], ["tickets-insights", "/tickets?tab=insights"],
  ["attendance-daily", "/attendance"], ["attendance-monthly", "/attendance?tab=monthly"], ["attendance-requests", "/attendance?tab=requests"],
  ["attendance-offices", "/attendance?tab=offices"],
  ["team", "/team"], ["stores", "/stores"], ["vendors", "/inventory"], ["cards", "/cards"], ["compliance", "/compliance"],
  ["billing", "/accounts"], ["reports", "/reports"], ["audit-log", "/activity"], ["account", "/account"],
];

const ONLY = process.env.ONLY ? process.env.ONLY.split(",") : null;
const browser = await chromium.launch({ executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "light" });
const page = await ctx.newPage();
page.on("pageerror", (e) => console.log("PAGE ERROR:", e.message.slice(0, 200)));

await page.goto(BASE + "/login");
await page.getByLabel("Employee ID").fill("ADMIN001");
await page.getByLabel("Password").fill("Pass@123");
await page.getByRole("button", { name: "Sign in" }).click();
await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 15000 });

// use the real toggle on the profile page
await page.goto(BASE + "/account");
await page.waitForSelector('button[role="switch"]');
const before = await page.evaluate(() => document.documentElement.classList.contains("dark"));
await page.click('button[role="switch"]');
const after = await page.evaluate(() => document.documentElement.classList.contains("dark"));
console.log(`toggle: dark before=${before} after=${after}`);

const audit = () => {
  const parse = (c) => {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const lum = ({ r, g, b }) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const bgOf = (el) => {
    for (let e = el; e; e = e.parentElement) {
      const c = parse(getComputedStyle(e).backgroundColor);
      if (c && c.a >= 0.5) return c;
    }
    return parse(getComputedStyle(document.body).backgroundColor) ?? { r: 255, g: 255, b: 255, a: 1 };
  };
  const out = { lowContrast: [], lightPanels: [] };
  const seen = new Set();
  for (const el of document.body.querySelectorAll("*")) {
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none" || cs.opacity === "0") continue;
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;
    const own = [...el.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim()).map((n) => n.textContent.trim()).join(" ");
    if (own) {
      const fg = parse(cs.color), bg = bgOf(el);
      if (fg && bg) {
        const l1 = lum(fg), l2 = lum(bg);
        const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
        if (ratio < 2.4) {
          const key = el.tagName + own.slice(0, 20);
          if (!seen.has(key)) { seen.add(key); out.lowContrast.push(`${el.tagName.toLowerCase()} "${own.slice(0, 40)}" ratio ${ratio.toFixed(1)} fg=${cs.color} bg=rgb(${bg.r},${bg.g},${bg.b}) cls=${String(el.className).slice(0, 60)}`); }
        }
      }
    }
    const own_bg = parse(cs.backgroundColor);
    if (own_bg && own_bg.a >= 0.7 && r.width * r.height > 6000 && lum(own_bg) > 0.55) {
      out.lightPanels.push(`${el.tagName.toLowerCase()} ${Math.round(r.width)}x${Math.round(r.height)} bg=${cs.backgroundColor} cls=${String(el.className).slice(0, 70)}`);
    }
  }
  out.lowContrast = out.lowContrast.slice(0, 8);
  out.lightPanels = out.lightPanels.slice(0, 8);
  return out;
};

let problems = 0;
for (const [name, path] of PAGES) {
  if (ONLY && !ONLY.includes(name)) continue;
  await page.goto(BASE + path);
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(700);
  const isDark = await page.evaluate(() => document.documentElement.classList.contains("dark"));
  await page.screenshot({ path: `${OUT}/${name}.png` });
  const res = await page.evaluate(audit);
  const n = res.lowContrast.length + res.lightPanels.length;
  problems += n;
  console.log(`${n === 0 ? "OK  " : "WARN"} ${name} (dark=${isDark})`);
  res.lowContrast.forEach((x) => console.log("   low-contrast:", x));
  res.lightPanels.forEach((x) => console.log("   light panel :", x));
}

// the login page (signed out) in dark mode too
await page.evaluate(() => fetch("/api/v1/auth/logout", { method: "POST" }).catch(() => {}));
await ctx.clearCookies();
await page.evaluate(() => { const t = localStorage.getItem("veekay-theme"); localStorage.clear(); localStorage.setItem("veekay-theme", t); });
await page.goto(BASE + "/login");
await page.waitForTimeout(500);
await page.screenshot({ path: `${OUT}/login.png` });
const login = await page.evaluate(audit);
console.log("login page:", login.lowContrast.length + login.lightPanels.length, "issues");
login.lowContrast.forEach((x) => console.log("   low-contrast:", x));
login.lightPanels.forEach((x) => console.log("   light panel :", x));

console.log("TOTAL ISSUES:", problems + login.lowContrast.length + login.lightPanels.length);
await browser.close();
