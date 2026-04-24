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

        const actionService = this.model?.action;
        if (!actionService) return;

        // BAR-TH-171
        const barth171Id = this.data.barth171_wizard_id;
        if (barth171Id) {
            this.data.barth171_wizard_id = "";
            if (this._changes) this._changes.barth171_wizard_id = "";
            if (this._values) this._values.barth171_wizard_id = "";
            await actionService.doAction({
                type: "ir.actions.act_window",
                name: "Paramètres BAR-TH-171",
                res_model: "ibatix.wizard.barth171",
                res_id: parseInt(barth171Id),
                views: [[false, "form"]],
                target: "new",
            });
            return;
        }

        // BAT-EN-111
        const baten111Id = this.data.baten111_wizard_id;
        if (baten111Id) {
            this.data.baten111_wizard_id = "";
            if (this._changes) this._changes.baten111_wizard_id = "";
            if (this._values) this._values.baten111_wizard_id = "";
            await actionService.doAction({
                type: "ir.actions.act_window",
                name: "Paramètres BAT-EN-111",
                res_model: "ibatix.wizard.baten111",
                res_id: parseInt(baten111Id),
                views: [[false, "form"]],
                target: "new",
            });
        }
    },
});
