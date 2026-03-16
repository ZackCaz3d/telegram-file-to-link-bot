(function () {
  const key = "admin-theme";

  // Theme
  const saved = localStorage.getItem(key);
  if (saved === "dark") {
    document.body.classList.add("dark");
  } else if (!saved && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    document.body.classList.add("dark");
  }

  const btn = document.getElementById("theme-toggle");
  if (btn) {
    btn.onclick = function () {
      document.body.classList.toggle("dark");
      localStorage.setItem(
        key,
        document.body.classList.contains("dark") ? "dark" : "light"
      );
    };
  }

  // Mobile sidebar
  const menuBtn = document.getElementById("mobile-menu-btn");
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebar-overlay");

  if (menuBtn && sidebar && overlay) {
    menuBtn.onclick = function () {
      sidebar.classList.toggle("open");
      overlay.classList.toggle("active");
    };

    overlay.onclick = function () {
      sidebar.classList.remove("open");
      overlay.classList.remove("active");
    };
  }
})();
