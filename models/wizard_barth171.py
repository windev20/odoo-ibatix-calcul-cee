from odoo import fields, models, _
from odoo.exceptions import UserError


class WizardBarTh171(models.TransientModel):
    _name = 'ibatix.wizard.barth171'
    _description = 'Paramètres BAR-TH-171'

    order_id = fields.Many2one('sale.order', required=True)
    product_id = fields.Many2one('product.product', string='Produit', readonly=True)

    surface_chauffee = fields.Float(
        string='Surface chauffée par le système (m²)',
        digits=(10, 2),
    )
    type_logement = fields.Selection([
        ('maison', 'Maison individuelle'),
        ('appartement', 'Appartement'),
    ], string='Type de logement')

    def action_confirm(self):
        self.ensure_one()
        if not self.surface_chauffee:
            raise UserError(_("Veuillez renseigner la surface chauffée."))
        if not self.type_logement:
            raise UserError(_("Veuillez renseigner le type de logement."))
        order = self.order_id

        # Chercher une ligne BAR-TH-171 avec ce produit sans surface_chauffee
        line = order.order_line.filtered(
            lambda l: l.product_id == self.product_id
            and l.operation_cee_id.code == 'BAR-TH-171'
            and not l.surface_chauffee_cee
        )[:1]

        if line:
            line.write({
                'surface_chauffee_cee': self.surface_chauffee,
                'type_logement_cee': self.type_logement,
            })
        else:
            # Ligne pas encore sauvegardée : stocker en attente sur l'order
            order.write({
                'barth171_surface_pending': self.surface_chauffee,
                'barth171_type_pending': self.type_logement,
                'barth171_product_pending': self.product_id.id,
            })

        return {'type': 'ir.actions.act_window_close'}
