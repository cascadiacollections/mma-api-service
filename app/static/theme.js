(function initializeTheme() {
  const storageKey = "mma-pickem-theme";
  const supportedThemes = new Set(["classic", "night"]);
  const selector = document.querySelector("#theme-select");
  const themeColor = document.querySelector('meta[name="theme-color"]');

  function applyTheme(theme) {
    const selectedTheme = supportedThemes.has(theme) ? theme : "classic";
    document.documentElement.dataset.theme = selectedTheme;
    if (selector) selector.value = selectedTheme;
    if (themeColor) {
      themeColor.content = selectedTheme === "night" ? "#0d0f12" : "#151515";
    }
  }

  let savedTheme = null;
  try {
    savedTheme = localStorage.getItem(storageKey);
  } catch {
    // Theme persistence is optional when storage is unavailable.
  }
  applyTheme(savedTheme);

  selector?.addEventListener("change", () => {
    applyTheme(selector.value);
    try {
      localStorage.setItem(storageKey, selector.value);
    } catch {
      // Keep the selected theme for this page even if persistence is blocked.
    }
  });
})();
