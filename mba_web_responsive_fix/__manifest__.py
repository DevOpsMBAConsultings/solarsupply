{
    "name": "MBA - Web Responsive Fix (URL Sync)",
    "summary": "Sincroniza la URL del navegador al abrir y cerrar el menú de aplicaciones de web_responsive",
    "version": "19.0.1.0.0",
    "category": "Extra Tools",
    "author": "MBA Consultings",
    "license": "LGPL-3",
    "depends": ["web", "web_responsive"],
    "assets": {
        "web.assets_backend": [
            "mba_web_responsive_fix/static/src/js/apps_menu_url_patch.esm.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
