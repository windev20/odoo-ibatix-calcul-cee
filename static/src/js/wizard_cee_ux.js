/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { useEffect } from "@odoo/owl";

const WIZARD_SELECT   = "ibatix.wizard.select.operation.cee";
const WIZARD_BARTH171 = "ibatix.wizard.barth171";
const WIZARD_MODELS   = new Set([WIZARD_SELECT, WIZARD_BARTH171]);

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);

        useEffect(
            () => {
                const model = this.props.resModel;
                if (!WIZARD_MODELS.has(model)) return () => {};

                // Auto-focus sur le premier champ au montage
                // On attend que le modal et ses champs soient dans le DOM
                let attempts = 0;
                const tryFocus = setInterval(() => {
                    const modal = document.querySelector(".modal");
                    const target = model === WIZARD_SELECT
                        ? modal?.querySelector(".o_field_many2one input")
                        : modal?.querySelector(".o_field_float input, input[type=number]");
                    if (target) {
                        target.focus();
                        clearInterval(tryFocus);
                    } else if (++attempts > 30) {
                        clearInterval(tryFocus);
                    }
                }, 80);

                // ── Gestion Tab : rediriger vers le bon élément ─────────────
                // On utilise requestAnimationFrame APRÈS le déplacement du focus
                // pour ne pas manipuler tabindex (que OWL écrase au re-render).
                const onTab = (ev) => {
                    if (ev.key !== "Tab" || ev.shiftKey) return;
                    requestAnimationFrame(() => {
                        const focused = document.activeElement;
                        if (!focused || !focused.closest(".modal")) return;

                        // Cas 1 : Tab atterrit sur le wrapper .o_field_radio
                        // → rediriger vers le radio coché ou le premier
                        if (focused.classList.contains("o_field_radio")) {
                            const dest =
                                focused.querySelector("input[type=radio]:checked") ||
                                focused.querySelector("input[type=radio]");
                            if (dest) { dest.focus(); return; }
                        }

                        // Cas 2 : Tab atterrit sur l'input du SelectMenu
                        // → simuler un clic pour ouvrir le dropdown immédiatement
                        if (
                            focused.classList.contains("o_select_menu_input") &&
                            focused.closest(".o_field_selection")
                        ) {
                            focused.click();
                        }
                    });
                };

                // ── Enter → valider (hors dropdown ouvert) ─────────────────
                const onKeydown = (ev) => {
                    if (ev.key === "Tab" && !ev.shiftKey) { onTab(ev); return; }
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
                    clearInterval(tryFocus);
                    document.removeEventListener("keydown", onKeydown, true);
                };
            },
            () => []
        );
    },
});
