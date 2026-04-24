/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { useEffect } from "@odoo/owl";

const WIZARD_SELECT   = "ibatix.wizard.select.operation.cee";
const WIZARD_BARTH171 = "ibatix.wizard.barth171";
const WIZARD_MODELS   = new Set([WIZARD_SELECT, WIZARD_BARTH171]);

function fixRadioTabindex(modal) {
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

                // ── Délai 200ms : attendre le rendu complet du formulaire ─
                setTimeout(() => {
                    const modal = document.querySelector(".modal");
                    if (!modal) return;

                    // Auto-focus sur le premier champ saisissable
                    const firstInput = model === WIZARD_SELECT
                        ? modal.querySelector(".o_field_many2one input")
                        : modal.querySelector(".o_field_float input, input[type=number]");
                    if (firstInput) firstInput.focus();

                    // Correction tabindex pour les groupes radio (si widget=radio)
                    fixRadioTabindex(modal);

                    // ── Auto-ouverture du SelectMenu Odoo 19 lors du Tab ──
                    // SelectMenu ne s'ouvre pas au focus — il faut un clic.
                    // On détecte que le dernier touch clavier était Tab, puis
                    // on clique l'input toggler pour propager au Dropdown.
                    let tabPressed = false;

                    modal.addEventListener("keydown", (ev) => {
                        tabPressed = ev.key === "Tab" && !ev.shiftKey;
                    }, true);

                    modal.addEventListener("focusin", (ev) => {
                        if (!tabPressed) return;
                        tabPressed = false;
                        const el = ev.target;
                        // L'input du SelectMenu a la classe o_select_menu_input
                        if (!el.classList.contains("o_select_menu_input")) return;
                        // S'assurer qu'on est sur un champ Selection dans ce modal
                        if (!el.closest(".o_field_selection")) return;
                        // Déclencher l'ouverture via click (propagé au Dropdown parent)
                        setTimeout(() => el.click(), 0);
                    });

                    // Mise à jour tabindex après sélection d'un radio
                    modal.addEventListener("change", (ev) => {
                        if (ev.target.type !== "radio") return;
                        const wrapper = ev.target.closest(".o_field_radio");
                        if (!wrapper) return;
                        [...wrapper.querySelectorAll("input[type=radio]")]
                            .forEach((r) => r.setAttribute("tabindex", "-1"));
                        ev.target.setAttribute("tabindex", "0");
                    });
                }, 200);

                // ── Enter → valider (hors dropdown ouvert) ───────────────
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
