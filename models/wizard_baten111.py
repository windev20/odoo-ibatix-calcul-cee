from odoo import fields, models, _
from odoo.exceptions import UserError


class WizardBatEn111(models.TransientModel):
    _name = 'ibatix.wizard.baten111'
    _description = 'Paramètres BAT-EN-111'

    order_id = fields.Many2one('sale.order', required=True)
    product_id = fields.Many2one('product.product', string='Produit', readonly=True)
    line_id = fields.Many2one('sale.order.line', string='Ligne CEE', readonly=True, ondelete='cascade')

    type_vmc = fields.Selection([
        ('naturelle', 'Ventilation naturelle'),
        ('simple_flux', 'VMC simple flux'),
        ('double_flux', 'VMC double flux'),
        ('parietodynamique', 'Vitrage pariétodynamique'),
        ('vec', 'VEC — Ventilation par extraction centralisée'),
    ], string='Système de ventilation dans les locaux', required=True)

    secteur_activite = fields.Selection([
        ('bureaux', 'Bureaux'),
        ('enseignement', 'Enseignement'),
        ('commerces', 'Commerces / Grande distribution'),
        ('hotellerie', 'Hôtellerie / Restauration'),
        ('sante', 'Santé / Médico-social'),
        ('logistique', 'Logistique / Entrepôts'),
        ('industrie', 'Industrie'),
        ('agriculture', 'Agriculture'),
        ('autre', 'Autre'),
    ], string="Secteur d'activité du bâtiment", required=True)

    def action_confirm(self):
        self.ensure_one()
        if not self.type_vmc:
            raise UserError(_("Veuillez renseigner le système de ventilation."))
        if not self.secteur_activite:
            raise UserError(_("Veuillez renseigner le secteur d'activité."))

        vals = {
            'type_vmc_cee': self.type_vmc,
            'secteur_activite_cee': self.secteur_activite,
        }

        # Cas 1 : ligne déjà sauvegardée (via + Opération CEE)
        if self.line_id:
            self.line_id.write(vals)
            return {'type': 'ir.actions.act_window_close'}

        # Cas 2 : ligne pas encore sauvegardée (via product_id onchange)
        order = self.order_id
        line = order.order_line.filtered(
            lambda l: l.operation_cee_id.code == 'BAT-EN-111'
            and not l.type_vmc_cee
        )[:1]

        if line:
            line.write(vals)
        else:
            order.write({
                'baten111_type_vmc_pending': self.type_vmc,
                'baten111_secteur_activite_pending': self.secteur_activite,
                'baten111_product_pending': self.product_id.id,
            })

        return {'type': 'ir.actions.act_window_close'}
