from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    delegataire_cee_id = fields.Many2one(
        'ibatix.delegataire.cee',
        string='Délégataire CEE',
        tracking=True,
    )
    contrat_cee_id = fields.Many2one(
        'ibatix.delegataire.contrat',
        string='Contrat CEE en cours',
        compute='_compute_contrat_cee',
        store=True,
        readonly=False,
        help="Contrat du délégataire dont la période couvre la date du devis.",
    )

    @api.depends('delegataire_cee_id', 'date_order')
    def _compute_contrat_cee(self):
        for order in self:
            if not order.delegataire_cee_id or not order.date_order:
                order.contrat_cee_id = False
                continue

            date_devis = order.date_order.date()
            contrat = order.delegataire_cee_id.contrat_ids.filtered(
                lambda c: (not c.date_debut or c.date_debut <= date_devis)
                and (not c.date_fin or c.date_fin >= date_devis)
            )
            order.contrat_cee_id = contrat[:1]
