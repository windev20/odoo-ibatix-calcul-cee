from odoo import fields, models


class WizardCeeManquants(models.TransientModel):
    _name = 'ibatix.wizard.cee.manquants'
    _description = "Données techniques CEE manquantes"

    sale_order_id = fields.Many2one('sale.order', required=True, readonly=True)
    message_html = fields.Html(readonly=True, sanitize=False)

    def action_confirmer_quand_meme(self):
        self.ensure_one()
        self.sale_order_id.with_context(skip_cee_check=True).button_confirm()
        return {'type': 'ir.actions.act_window_close'}
