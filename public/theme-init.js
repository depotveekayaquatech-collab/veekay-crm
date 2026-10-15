// Applies the saved dark theme before first paint. A file (not inline) so the Content-Security-Policy `script-src 'self'` allows it.
try {
  if (localStorage.getItem("veekay-theme") === "dark") {
    document.documentElement.classList.add("dark");
    document.querySelector('meta[name="theme-color"]').setAttribute("content", "#0f1328");
  }
} catch (e) {}
