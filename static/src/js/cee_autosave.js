/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { ViewButton } from "@web/views/view_button/view_button";

patch(ViewButton.prototype, {
    async onClick(ev, newWindow) {
        if (this.clickParams.name === "action_ouvrir_wizard_cee") {
            const record = this.props.record;
            if (record) {
                const root = record.model.root;
                if (root && (root.isNew || root.isDirty)) {
                    await root.save({ stayInEdition: true });
                }
            }
        }
        return super.onClick(ev, newWindow);
    },
});
