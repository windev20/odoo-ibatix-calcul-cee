from odoo import fields, models
from odoo.exceptions import UserError


class WizardSelectOperationCee(models.TransientModel):
    _name = 'ibatix.wizard.select.operation.cee'
    _description = "Sélection d'une opération CEE"

    order_id = fields.Many2one('sale.order', required=True, ondelete='cascade')
    operation_cee_id = fields.Many2one('ibatix.operation.cee', string='Opération CEE')

    def action_confirmer(self):
        self.ensure_one()
        if not self.operation_cee_id:
            raise UserError("Veuillez sélectionner une opération CEE.")
        op = self.operation_cee_id
        name = f"{op.code} — {op.name}" if op.code else op.name
        lines = self.order_id.order_line
        seq = (max(lines.mapped('sequence'), default=10) + 1) if lines else 10
        line = self.env['sale.order.line'].create({
            'order_id': self.order_id.id,
            'display_type': 'line_cee',
            'name': name,
            'operation_cee_id': op.id,
            'sequence': seq,
            'product_uom_qty': 0,
            'price_unit': 0,
        })

        if op.code == 'BAR-TH-171':
            wizard = self.env['ibatix.wizard.cee.simple'].create({'line_id': line.id})
            return {
                'type': 'ir.actions.act_window',
                'name': "Paramètres — BAR-TH-171",
                'res_model': 'ibatix.wizard.cee.simple',
                'res_id': wizard.id,
                'view_mode': 'form',
                'target': 'new',
            }

        if op.code == 'BAT-EN-111':
            wizard = self.env['ibatix.wizard.baten111'].create({
                'order_id': self.order_id.id,
                'line_id': line.id,
            })
            return {
                'type': 'ir.actions.act_window',
                'name': "Paramètres — BAT-EN-111",
                'res_model': 'ibatix.wizard.baten111',
                'res_id': wizard.id,
                'view_mode': 'form',
                'target': 'new',
            }

        return {'type': 'ir.actions.act_window_close'}
