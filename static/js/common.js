/**
 * Shared client utilities.
 *
 * Loaded once in base.html (before the inline page scripts) and exposed as
 * window.App.* so every page uses one implementation instead of redefining
 * escapeHtml / fetch wrappers per template (the source of several drift bugs).
 */
(function () {
    'use strict';
    const App = (window.App = window.App || {});

    /** HTML-escape text for safe insertion into innerHTML / template literals. */
    App.escapeHtml = function (text) {
        const div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    };

    /** Escape for use inside a double-quoted HTML attribute. */
    App.escapeAttr = function (text) {
        return App.escapeHtml(text).replace(/"/g, '&quot;');
    };

    /**
     * fetch() that returns the parsed JSON body.
     *
     * The API returns {success, error} with non-2xx status codes, so we parse
     * the body regardless of status and let the caller check `.success`. But we
     * throw a clear error (instead of an opaque "Unexpected token <" JSON parse
     * failure) when the body isn't JSON at all — e.g. an HTML 500 page.
     */
    App.fetchJSON = async function (url, options) {
        options = options || {};
        const headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
        const resp = await fetch(url, Object.assign({}, options, { headers }));
        try {
            return await resp.json();
        } catch (e) {
            throw new Error('HTTP ' + resp.status + ' (non-JSON response from ' + url + ')');
        }
    };

    /** Trailing-edge debounce. */
    App.debounce = function (fn, wait) {
        let timer = null;
        return function () {
            const ctx = this, args = arguments;
            clearTimeout(timer);
            timer = setTimeout(function () { fn.apply(ctx, args); }, wait);
        };
    };
})();
