// ToDo theme toggle - dark / light, remembered in the browser

(function () {
    var btn = document.getElementById("themeBtn");
    if (!btn) return;

    function paint() {
        var theme = document.documentElement.getAttribute("data-theme") || "dark";
        btn.textContent = theme === "dark" ? "☀️" : "🌙";
        btn.title = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
    }

    btn.addEventListener("click", function () {
        var current = document.documentElement.getAttribute("data-theme") || "dark";
        var next = current === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        try {
            localStorage.setItem("todo-theme", next);
        } catch (e) { }
        paint();
    });

    paint();
})();

// 3-dots menu - open on tap, close on tap outside
(function () {
    var btn = document.getElementById("menuBtn");
    var menu = document.getElementById("menuDropdown");
    if (!btn || !menu) return;

    btn.addEventListener("click", function (e) {
        e.stopPropagation();
        menu.classList.toggle("open");
    });

    document.addEventListener("click", function () {
        menu.classList.remove("open");
    });
})();

// Auto-fill today's date + current time in the add-task form.
// Only fills empty fields, so the user can still change them
// (and the edit page keeps its existing values).
(function () {
    var dateInput = document.getElementById("dueDate");
    var timeInput = document.getElementById("dueTime");
    if (!dateInput && !timeInput) return;
    var now = new Date();
    function pad(n) {
        return String(n).padStart(2, "0");
    }
    if (dateInput && !dateInput.value) {
        dateInput.value =
            now.getFullYear() + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate());
    }
    if (timeInput && !timeInput.value) {
        timeInput.value = pad(now.getHours()) + ":" + pad(now.getMinutes());
    }
})();