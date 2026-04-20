/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { Record } from "@web/model/relational_model/record";

patch(Record.prototype, {
    async _update(changes, options = {}) {
        // Capture BEFORE super mutates the changes object (Many2one fields can be deleted)
        const isSOLine = this.resModel === "sale.order.line";
        const hasProductChange = isSOLine && "product_id" in changes;

        await super._update(changes, options);

        if (!hasProductChange) return;

        const wizardId = this.data.barth171_wizard_id;
        if (!wizardId) return;

        // Effacer pour ne pas re-déclencher
        this.data.barth171_wizard_id = "";
        if (this._changes) this._changes.barth171_wizard_id = "";
        if (this._values) this._values.barth171_wizard_id = "";

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
