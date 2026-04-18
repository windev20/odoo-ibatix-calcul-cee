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
    total_prime_cee = fields.Float(
        string='Total Prime CEE',
        compute='_compute_prime_cee_totals',
        store=True,
        digits=(10, 2),
    )
    prime_cee_label = fields.Char(
        string='Libellé Prime CEE',
        compute='_compute_prime_cee_totals',
        store=True,
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

    @api.depends('order_line.prime_cee', 'order_line.operation_cee_id', 'delegataire_cee_id')
    def _compute_prime_cee_totals(self):
        for order in self:
            lines_with_prime = order.order_line.filtered(lambda l: l.prime_cee)
            order.total_prime_cee = sum(lines_with_prime.mapped('prime_cee'))
            if lines_with_prime and order.delegataire_cee_id:
                codes = ' '.join(dict.fromkeys(
                    l.operation_cee_id.code
                    for l in lines_with_prime
                    if l.operation_cee_id and l.operation_cee_id.code
                ))
                delegataire = order.delegataire_cee_id.name or ''
                order.prime_cee_label = f"Prime {codes} {delegataire}".strip() if codes else f"Prime CEE {delegataire}".strip()
            else:
                order.prime_cee_label = 'Prime CEE'
