/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { useEffect } from "@odoo/owl";

const WIZARD_SELECT   = "ibatix.wizard.select.operation.cee";
const WIZARD_BARTH171 = "ibatix.wizard.barth171";
const WIZARD_MODELS   = new Set([WIZARD_SELECT, WIZARD_BARTH171]);

function fixRadioTabindex(modal) {
    // Le composant Field ajoute tabindex sur le wrapper .o_field_radio
    // ce qui fait que Tab atterrit sur le div, pas sur les <input type=radio>.
    // On exclut le wrapper et on rend tabbable uniquement le radio coché (ou le premier).
    modal.querySelectorAll(".o_field_radio").forEach((wrapper) => {
        wrapper.setAttribute("tabindex", "-1");
        const radios = [...wrapper.querySelectorAll("input[type=radio]")];
        if (!radios.length) return;
        radios.forEach((r) => r.setAttribute("tabindex", "-1"));
        const tabbable = radios.find((r) => r.checked) || radios[0];
        tabbable.setAttribute("tabindex", "0");
    });
}

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);

        useEffect(
            () => {
                const model = this.props.resModel;
                if (!WIZARD_MODELS.has(model)) return () => {};

                setTimeout(() => {
                    const modal = document.querySelector(".modal");
                    if (!modal) return;

                    // Auto-focus sur le premier champ saisissable
                    const firstInput = model === WIZARD_SELECT
                        ? modal.querySelector(".o_field_many2one input")
                        : modal.querySelector(".o_field_float input, input[type=number]");
                    if (firstInput) firstInput.focus();

                    // Correction des tabindex radio
                    fixRadioTabindex(modal);

                    // Quand l'utilisateur change de radio via les flèches,
                    // mettre à jour quel radio est tabbable pour le prochain Tab.
                    modal.addEventListener("change", (ev) => {
                        if (ev.target.type !== "radio") return;
                        const wrapper = ev.target.closest(".o_field_radio");
                        if (!wrapper) return;
                        [...wrapper.querySelectorAll("input[type=radio]")]
                            .forEach((r) => r.setAttribute("tabindex", "-1"));
                        ev.target.setAttribute("tabindex", "0");
                    });
                }, 80);

                // Enter → valider quand aucun dropdown n'est ouvert
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
