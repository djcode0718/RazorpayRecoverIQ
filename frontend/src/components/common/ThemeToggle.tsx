import { useEffect, useState } from "react";

export type Theme = "dark" | "light";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem("recoveriq_theme");
    return (saved === "light" || saved === "dark") ? saved : "dark";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("recoveriq_theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  };

  return (
    <button
      onClick={toggleTheme}
      className="theme-toggle-btn"
      title={`Switch to ${theme === "dark" ? "Light" : "Dark"} Mode`}
      aria-label={`Switch to ${theme === "dark" ? "Light" : "Dark"} Mode`}
    >
      <span className="theme-toggle-icon">{theme === "dark" ? "☀️" : "🌙"}</span>
      <span className="theme-toggle-label">{theme === "dark" ? "Light Mode" : "Dark Mode"}</span>
    </button>
  );
}
