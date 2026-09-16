/** @odoo-module **/

import { Component, useState, useRef, onMounted } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";

export class DgiNumberPopup extends Component {
    static template = "mba_pa_pos.DgiNumberPopup";
    static components = { Dialog };
    static props = {
        title: { type: String, optional: true },
        startingValue: { type: String, optional: true },
        getPayload: Function,
        close: Function,
    };
    static defaultProps = {
        title: _t("Confirmar Número de Factura DGI (PAC)"),
        startingValue: "0000000001",
    };

    setup() {
        this.state = useState({
            inputValue: String(this.props.startingValue || ""),
        });
        this.inputRef = useRef("input");
        onMounted(() => {
            if (this.inputRef.el) {
                this.inputRef.el.focus();
                this.inputRef.el.select();
            }
        });
    }

    confirm() {
        const val = String(this.state.inputValue || "").trim();
        this.props.getPayload(val);
        this.props.close();
    }

    cancel() {
        this.props.close();
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            ev.stopPropagation();
            this.confirm();
        }
    }
}
