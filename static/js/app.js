/* Airlock — Web UI */

(function () {
    "use strict";

    var TOKEN_KEY = "airlock_session_token";

    function getToken() {
        return sessionStorage.getItem(TOKEN_KEY);
    }

    function setToken(token) {
        sessionStorage.setItem(TOKEN_KEY, token);
    }

    function clearToken() {
        sessionStorage.removeItem(TOKEN_KEY);
    }

    async function apiGet(path) {
        var token = getToken();
        var headers = {};
        if (token) headers["Authorization"] = "Bearer " + token;
        return fetch(path, { headers: headers });
    }

    async function apiPost(path, body) {
        var token = getToken();
        var headers = { "Content-Type": "application/json" };
        if (token) headers["Authorization"] = "Bearer " + token;
        return fetch(path, {
            method: "POST",
            headers: headers,
            body: JSON.stringify(body),
        });
    }

    function showError(el, msg) {
        el.textContent = msg;
        el.hidden = false;
    }

    /* ---- Login / Setup Page ---- */

    var setupForm = document.getElementById("setup-form");
    var loginForm = document.getElementById("login-form");
    var loadingMsg = document.getElementById("loading-msg");

    if (setupForm && loginForm) {
        /* Check if already authenticated */
        if (getToken()) {
            apiGet("/api/admin/stats").then(function (res) {
                if (res.ok) {
                    window.location.href = "/ui/dashboard.html";
                    return;
                }
                clearToken();
                initLoginPage();
            }).catch(function () {
                clearToken();
                initLoginPage();
            });
        } else {
            initLoginPage();
        }

        function initLoginPage() {
            /* Check setup status */
            fetch("/api/admin/status")
                .then(function (res) { return res.json(); })
                .then(function (data) {
                    if (loadingMsg) loadingMsg.hidden = true;
                    if (data.setup_required) {
                        setupForm.hidden = false;
                    } else {
                        loginForm.hidden = false;
                    }
                })
                .catch(function () {
                    if (loadingMsg) loadingMsg.textContent = "Cannot reach Airlock server.";
                });
        }

        /* Setup form */
        setupForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            var password = document.getElementById("setup-password").value;
            var confirm = document.getElementById("setup-confirm").value;
            var errorEl = document.getElementById("setup-error");
            var btn = document.getElementById("setup-btn");

            errorEl.hidden = true;

            if (password !== confirm) {
                showError(errorEl, "Passwords do not match.");
                return;
            }

            if (password.length < 8) {
                showError(errorEl, "Password must be at least 8 characters.");
                return;
            }

            btn.disabled = true;
            btn.textContent = "Setting up...";

            try {
                var res = await apiPost("/api/admin/setup", { password: password });
                var data = await res.json();
                if (res.ok) {
                    setToken(data.token);
                    window.location.href = "/ui/dashboard.html";
                } else {
                    showError(errorEl, data.detail || "Setup failed.");
                }
            } catch (err) {
                showError(errorEl, "Connection error.");
            } finally {
                btn.disabled = false;
                btn.textContent = "Create Admin Account";
            }
        });

        /* Login form */
        loginForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            var password = document.getElementById("login-password").value;
            var errorEl = document.getElementById("login-error");
            var btn = document.getElementById("login-btn");

            errorEl.hidden = true;
            btn.disabled = true;
            btn.textContent = "Signing in...";

            try {
                var res = await apiPost("/api/admin/login", { password: password });
                var data = await res.json();
                if (res.ok) {
                    setToken(data.token);
                    window.location.href = "/ui/dashboard.html";
                } else {
                    showError(errorEl, data.detail || "Invalid password.");
                }
            } catch (err) {
                showError(errorEl, "Connection error.");
            } finally {
                btn.disabled = false;
                btn.textContent = "Sign In";
            }
        });
    }

    /* ---- Dashboard Page ---- */

    var logoutBtn = document.getElementById("logout-btn");
    if (logoutBtn) {
        /* Check auth on load */
        if (!getToken()) {
            window.location.href = "/ui/";
            return;
        }

        apiGet("/api/admin/stats").then(function (res) {
            if (!res.ok) {
                clearToken();
                window.location.href = "/ui/";
                return;
            }
            return res.json();
        }).then(function (data) {
            if (!data) return;
            var credEl = document.getElementById("stat-credentials");
            var profEl = document.getElementById("stat-profiles");
            var execEl = document.getElementById("stat-executions");
            if (credEl) credEl.textContent = data.stored_credentials;
            if (profEl) profEl.textContent = data.active_profiles;
            if (execEl) execEl.textContent = data.total_executions;
        });

        /* Nav switching */
        document.querySelectorAll(".nav-item").forEach(function (item) {
            item.addEventListener("click", function (e) {
                e.preventDefault();
                var section = this.dataset.section;

                document.querySelectorAll(".nav-item").forEach(function (n) {
                    n.classList.remove("active");
                });
                this.classList.add("active");

                document.querySelectorAll(".section").forEach(function (s) {
                    s.classList.remove("active");
                });
                var target = document.getElementById("section-" + section);
                if (target) target.classList.add("active");
            });
        });

        /* Logout */
        logoutBtn.addEventListener("click", function () {
            clearToken();
            window.location.href = "/ui/";
        });
    }
})();
