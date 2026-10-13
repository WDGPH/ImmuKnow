import darkIcon from "./assets/studio-icon-dark.svg";
import lightIcon from "./assets/studio-icon-light.svg";

export function initializeTheme() {
  const key = "immuknow:theme";
  const system = matchMedia("(prefers-color-scheme: dark)");
  const button = document.getElementById("theme-toggle") as HTMLButtonElement;
  let preference: string | null = null;
  try {
    preference = localStorage.getItem(key);
  } catch {
    /* Use the system theme when storage is unavailable. */
  }
  const apply = (dark: boolean) => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    (document.getElementById("favicon") as HTMLLinkElement).href = dark ? darkIcon : lightIcon;
    const label = `Switch to ${dark ? "light" : "dark"} mode`;
    button.setAttribute("aria-label", label);
    button.title = label;
    button.innerHTML = dark
      ? '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></svg>'
      : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.4 13A8.5 8.5 0 0 1 11 3.6 8.5 8.5 0 1 0 20.4 13Z"/></svg>';
  };
  apply(preference === "dark" || (preference !== "light" && system.matches));
  button.onclick = () => {
    preference = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    apply(preference === "dark");
    try {
      localStorage.setItem(key, preference);
    } catch {
      /* The theme still works for this session. */
    }
  };
  system.addEventListener("change", () => {
    if (preference !== "light" && preference !== "dark") apply(system.matches);
  });
}
