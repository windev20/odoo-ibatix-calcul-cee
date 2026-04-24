/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { useEffect } from "@odoo/owl";

const WIZARD_MODEL = "ibatix.wizard.select.operation.cee";

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);

        // useEffect doit toujours être appelé (règle des hooks OWL)
        useEffect(
            () => {
                if (this.props.resModel !== WIZARD_MODEL) return () => {};

                // Auto-focus sur le champ Many2one (délai pour l'animation du dialog)
                setTimeout(() => {
                    const input = document.querySelector(".modal .o_field_many2one input");
                    if (input) input.focus();
                }, 80);

                // Enter → valider le wizard quand le dropdown est fermé
                const onKeydown = (ev) => {
                    if (ev.key !== "Enter") return;
                    // Laisser le dropdown gérer son propre Enter (sélection d'option)
                    if (document.querySelector(".o-dropdown--menu")) return;
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
