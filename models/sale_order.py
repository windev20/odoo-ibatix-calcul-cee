from collections import defaultdict

from odoo import api, fields, models


def _fmt_euro(amount):
    """Formate un montant en euros au format français : 1 500,00 €"""
    s = f"{amount:,.2f}"
    entier, dec = s.split('.')
    entier = entier.replace(',', '\u202f')  # espace fine insécable
    return f"{entier},{dec}\u00a0€"


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
    # Conservé pour compatibilité ascendante (rapports, etc.)
    prime_cee_label = fields.Char(
        string='Libellé Prime CEE',
        compute='_compute_prime_cee_totals',
        store=True,
    )
    # Rendu HTML : une ligne par opération CEE
    prime_cee_details_html = fields.Html(
        compute='_compute_prime_cee_totals',
        store=False,
        sanitize=False,
        string='Détail primes CEE',
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

            if not lines_with_prime:
                order.prime_cee_label = ''
                order.prime_cee_details_html = False
                continue

            delegataire_name = order.delegataire_cee_id.name or ''

            # Grouper par code opération pour cumuler les lignes du même type
            grouped = defaultdict(float)
            for line in lines_with_prime:
                code = (line.operation_cee_id.code or '') if line.operation_cee_id else ''
                grouped[code] += line.prime_cee

            # Libellé global (compat)
            codes_str = ' '.join(c for c in grouped if c)
            order.prime_cee_label = (
                f"Prime {codes_str} {delegataire_name}".strip()
                if codes_str else f"Prime CEE {delegataire_name}".strip()
            )

            # HTML : une ligne par opération
            rows = []
            for code, amount in grouped.items():
                label = (
                    f"Prime CEE {code} {delegataire_name}".strip()
                    if code else f"Prime CEE {delegataire_name}".strip()
                )
                rows.append(
                    f'<div class="d-flex justify-content-between fw-bold text-success border-top pt-1 mt-1" '
                    f'style="width:100%;gap:1rem;">'
                    f'<span style="flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{label}</span>'
                    f'<span style="white-space:nowrap;text-align:right;">{_fmt_euro(amount)}</span>'
                    f'</div>'
                )
            order.prime_cee_details_html = ''.join(rows)
