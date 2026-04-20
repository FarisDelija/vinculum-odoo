/*
 * Injects the Vinc design-system fonts into document.head exactly once.
 * Loaded via web.assets_backend so it runs on every backend page the user
 * opens — the browser cache handles dedup across requests.
 *
 * Why not @import in dashboard.css? Odoo's CSS bundler mangles @import
 * lines whose URL contains ';' (we use wght@400;500 for JetBrains Mono),
 * breaking the rule and the styles after it.
 */
(function () {
    "use strict";
    if (typeof document === "undefined") { return; }
    if (document.getElementById("vg-google-fonts")) { return; }

    var link = document.createElement("link");
    link.id = "vg-google-fonts";
    link.rel = "stylesheet";
    link.href =
        "https://fonts.googleapis.com/css2" +
        "?family=Fraunces:opsz,wght,SOFT@9..144,300..900,0..100" +
        "&family=DM+Sans:opsz,wght@9..40,400..600" +
        "&family=JetBrains+Mono:wght@400;500" +
        "&display=swap";
    (document.head || document.documentElement).appendChild(link);
})();
