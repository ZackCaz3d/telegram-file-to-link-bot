/**
 * Copyright 2025 Aman
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 */

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
