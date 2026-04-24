/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { useEffect } from "@odoo/owl";

const WIZARD_SELECT  = "ibatix.wizard.select.operation.cee";
const WIZARD_BARTH171 = "ibatix.wizard.barth171";
const WIZARD_MODELS = new Set([WIZARD_SELECT, WIZARD_BARTH171]);

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);

        useEffect(
            () => {
                const model = this.props.resModel;
                if (!WIZARD_MODELS.has(model)) return () => {};

                // ── Auto-focus au montage ─────────────────────────────────
                setTimeout(() => {
                    const input = model === WIZARD_SELECT
                        ? document.querySelector(".modal .o_field_many2one input")
                        : document.querySelector(".modal .o_field_float input, .modal input[type=number]");
                    if (input) input.focus();
                }, 80);

                // ── Redirection focus sur les groupes radio ───────────────
                // Le Tab atterrit sur .o_field_radio (wrapper) au lieu d'un
                // <input type=radio> → on le redirige immédiatement vers le
                // radio coché (ou le premier si rien n'est coché).
                const onFocus = (ev) => {
                    if (!ev.target.classList.contains("o_field_radio")) return;
                    if (!ev.target.closest(".modal")) return;
                    const dest =
                        ev.target.querySelector("input[type=radio]:checked") ||
                        ev.target.querySelector("input[type=radio]");
                    if (dest) dest.focus();
                };
                document.addEventListener("focus", onFocus, true);

                // ── Enter → valider (hors dropdown ouvert) ────────────────
                const onKeydown = (ev) => {
                    if (ev.key !== "Enter") return;
                    if (document.querySelector(".o-autocomplete--dropdown-menu, .o-dropdown--menu")) return;
                    const btn = document.querySelector(".modal .modal-footer .btn-primary");
                    if (btn) {
                        ev.preventDefault();
                        ev.stopPropagation();
                        btn.click();
                    }
                };
                document.addEventListener("keydown", onKeydown, true);

                return () => {
                    document.removeEventListener("focus", onFocus, true);
                    document.removeEventListener("keydown", onKeydown, true);
                };
            },
            () => []
        );
    },
});
