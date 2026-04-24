/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { useEffect } from "@odoo/owl";

const WIZARD_SELECT = "ibatix.wizard.select.operation.cee";
const WIZARD_BARTH171 = "ibatix.wizard.barth171";

const WIZARD_MODELS = new Set([WIZARD_SELECT, WIZARD_BARTH171]);

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);

        useEffect(
            () => {
                const model = this.props.resModel;
                if (!WIZARD_MODELS.has(model)) return () => {};

                // Auto-focus : Many2one pour le wizard sélection, premier input sinon
                setTimeout(() => {
                    const input =
                        model === WIZARD_SELECT
                            ? document.querySelector(".modal .o_field_many2one input")
                            : document.querySelector(".modal .o_field_float input, .modal input[type='number']");
                    if (input) input.focus();
                }, 80);

                // Enter → valider quand aucun dropdown/autocomplete n'est ouvert
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
                return () => document.removeEventListener("keydown", onKeydown, true);
            },
            () => []
        );
    },
});
