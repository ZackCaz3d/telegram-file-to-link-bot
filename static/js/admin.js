(function () {
  const key = "admin-theme";
  const btn = document.getElementById("theme-toggle");

  if (!btn) return;

  const saved = localStorage.getItem(key);

  if (saved === "dark") {
    document.body.classList.add("dark");
  } else if (!saved) {
    if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
      document.body.classList.add("dark");
    }
  }

  btn.onclick = () => {
    document.body.classList.toggle("dark");
    localStorage.setItem(
      key,
      document.body.classList.contains("dark") ? "dark" : "light"
    );
  };
})();
