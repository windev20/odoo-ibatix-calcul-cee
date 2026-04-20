/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { Record } from "@web/model/relational_model/record";

patch(Record.prototype, {
    async _update(changes, options = {}) {
        await super._update(changes, options);

        if (this.resModel !== "sale.order.line") return;
        if (!("product_id" in changes)) return;

        const wizardId = this.data.barth171_wizard_id;
        if (!wizardId) return;

        // Effacer pour ne pas re-déclencher
        this._values.barth171_wizard_id = "";
        Object.assign(this.data, this._values, this._changes || {});

        // Action service disponible sur le modèle racine
        const actionService = this.model?.action;
        if (!actionService) return;

        await actionService.doAction({
            type: "ir.actions.act_window",
            name: "Paramètres BAR-TH-171",
            res_model: "ibatix.wizard.barth171",
            res_id: parseInt(wizardId),
            views: [[false, "form"]],
            target: "new",
        });
    },
});
