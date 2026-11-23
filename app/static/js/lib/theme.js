// Dark is the default; the choice is remembered in this browser only.
const KEY = "theme";
function apply(light) {
  document.documentElement.classList.toggle("dark", !light);
}
function save(light) {
  try { localStorage.setItem(KEY, light ? "light" : "dark"); } catch (e) { /* storage unavailable */ }
}
const btn = document.getElementById("theme-toggle");
if (btn) {
  btn.addEventListener("click", () => {
    const light = document.documentElement.classList.contains("dark");
    apply(light);
    save(light);
  });
}
