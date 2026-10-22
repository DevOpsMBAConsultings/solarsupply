/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { browser } from "@web/core/browser/browser";
import { AppsMenu } from "@web_responsive/components/apps_menu/apps_menu.esm";

let previousUrl = null;

patch(AppsMenu.prototype, {
    setOpenState(openState) {
        super.setOpenState(openState);

        if (openState) {
            // Guardar la URL actual de la pantalla activa
            previousUrl = browser.location.pathname + browser.location.search + browser.location.hash;
            // Actualizar la barra de navegación a /odoo limpiamente sin recargar la página
            if (browser.location.pathname !== "/odoo") {
                browser.history.replaceState(browser.history.state, "", "/odoo");
            }
        } else if (previousUrl) {
            // Si el menú se cierra sin haber navegado a una app (ej. Escape o re-click en el botón)
            if (browser.location.pathname === "/odoo") {
                browser.history.replaceState(browser.history.state, "", previousUrl);
            }
            previousUrl = null;
        }
    },
});
