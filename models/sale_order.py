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

    # Valeurs en attente pour BAR-TH-171 (ligne pas encore sauvegardée en base)
    barth171_surface_pending = fields.Float(default=0.0)
    barth171_type_pending = fields.Char(default='')
    barth171_energie_pending = fields.Char(default='')
    barth171_product_pending = fields.Integer(default=0)

    delegataire_cee_id = fields.Many2one(
        'ibatix.delegataire.cee',
        string='Délégataire CEE',
        tracking=True,
        default=lambda self: self.env['ibatix.delegataire.cee'].search([('is_default', '=', True)], limit=1),
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
    total_prime_mpr = fields.Float(
        string='Total Prime MPR',
        compute='_compute_total_prime_mpr',
        store=True,
        digits=(10, 2),
    )
    prime_mpr_details_html = fields.Html(
        compute='_compute_prime_mpr_details_html',
        store=False,
        sanitize=False,
        string='Detail primes MPR',
    )

    @api.depends('order_line.prime_mpr')
    def _compute_total_prime_mpr(self):
        for order in self:
            order.total_prime_mpr = sum(
                order.order_line.filtered(lambda l: l.prime_mpr).mapped('prime_mpr')
            )

    @api.depends('order_line.prime_mpr', 'order_line.prime_mpr_ecrete', 'order_line.operation_cee_id')
    def _compute_prime_mpr_details_html(self):
        for order in self:
            lines_with_mpr = order.order_line.filtered(lambda l: l.prime_mpr)

            if not lines_with_mpr:
                order.prime_mpr_details_html = False
                continue

            grouped = defaultdict(float)
            for line in lines_with_mpr:
                code = (line.operation_cee_id.code or '') if line.operation_cee_id else ''
                grouped[code] += line.prime_mpr

            rows = []
            for code, amount in grouped.items():
                label = ("MaPrimeRenov' " + code).strip() if code else "MaPrimeRenov'"
                ecrete = any(
                    l.prime_mpr_ecrete
                    for l in lines_with_mpr
                    if (l.operation_cee_id.code if l.operation_cee_id else '') == code
                )
                if ecrete:
                    label += ' (ecrete)'
                rows.append(
                    '<div class="d-flex justify-content-between fw-bold text-primary border-top pt-1 mt-1" '
                    'style="width:100%;gap:1rem;">'
                    '<span style="flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
                    + label +
                    '</span>'
                    '<span style="white-space:nowrap;text-align:right;">'
                    + _fmt_euro(amount) +
                    '</span>'
                    '</div>'
                )
            order.prime_mpr_details_html = ''.join(rows)

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

    # ── Validation des données CEE à la confirmation ─────────────────────────

    _CEE_CHAMP_TO_LINE_FIELD = {
        'surface_m2':            ('surface_m2_cee',           'Surface (m²)'),
        'surface_chauffee':      ('surface_chauffee_cee',     'Surface chauffée (m²)'),
        'resistance_thermique':  ('resistance_thermique_cee', 'Résistance thermique R'),
        'puissance_kw':          ('puissance_kw_cee',         'Puissance (kW)'),
        'cop':                   ('cop_cee',                  'COP'),
        'scop':                  ('scop_cee',                 'SCOP'),
        'etas':                  ('etas_cee',                 'Efficacité saisonnière ηs (%)'),
        'nb_logements':          ('nb_logements_cee',         'Nombre de logements'),
        'type_logement':         ('type_logement_cee',        'Type de logement'),
        'zone_climatique':       ('zone_climatique_cee',      'Zone climatique'),
        'facteur_zone':          ('zone_climatique_cee',      'Zone climatique'),
        'facteur_logement':      ('type_logement_cee',        'Type de logement'),
        'profil_soutirage':      ('profil_soutirage_cee',     'Profil de soutirage'),
        'efficacite_energetique':('efficacite_energetique_cee','Efficacité énergétique (%)'),
    }

    def _check_cee_data_completeness(self):
        """
        Vérifie que les champs requis par chaque opération CEE sont remplis.
        Retourne un HTML listant les problèmes, ou '' si tout est OK.
        """
        issues = []
        for line in self.order_line.filtered('operation_cee_id'):
            op = line.operation_cee_id
            champs_requis = [
                c.strip()
                for c in (op.champs_requis or '').split(',')
                if c.strip()
            ]
            if not champs_requis:
                continue  # Opération non encore analysée — pas de vérification

            missing = []

            # Marque et modèle toujours obligatoires
            if not line.marque_cee:
                missing.append('Marque')
            if not line.modele_cee:
                missing.append('Modèle / Référence')

            seen = set()
            for champ in champs_requis:
                mapping = self._CEE_CHAMP_TO_LINE_FIELD.get(champ)
                if not mapping:
                    continue
                field_name, label = mapping
                if field_name in seen:
                    continue
                seen.add(field_name)
                if not getattr(line, field_name, None):
                    missing.append(label)

            if missing:
                next_line = line._get_next_product_line()
                product_label = (
                    next_line.product_id.name or '' if next_line else ''
                )
                issues.append({
                    'op_code': op.code or op.name or '',
                    'op_name': op.name or '',
                    'product': product_label,
                    'missing': missing,
                })

        if not issues:
            return ''

        rows = ''.join(
            f'<tr>'
            f'<td><strong>{i["op_code"]}</strong>'
            f'{"<br/><small class=text-muted>" + i["op_name"] + "</small>" if i["op_name"] != i["op_code"] else ""}'
            f'</td>'
            f'<td>{i["product"]}</td>'
            f'<td><span class="text-danger">{", ".join(i["missing"])}</span></td>'
            f'</tr>'
            for i in issues
        )

        return (
            '<div class="alert alert-warning mb-3">'
            '<h5 class="alert-heading">&#9888; Données techniques CEE incomplètes</h5>'
            '<p class="mb-0">Les champs suivants sont manquants pour calculer les primes CEE :</p>'
            '</div>'
            '<table class="table table-sm table-bordered">'
            '<thead class="table-light">'
            '<tr><th>Opération CEE</th><th>Produit associé</th><th>Champs manquants</th></tr>'
            '</thead>'
            f'<tbody>{rows}</tbody>'
            '</table>'
            '<div class="alert alert-info mt-2 mb-0">'
            '<small>&#128161; Cliquez sur la calculatrice &#129518; de chaque ligne pour '
            'saisir les données manquantes, ou confirmez quand même.</small>'
            '</div>'
        )

    def button_confirm(self):
        if self.env.context.get('skip_cee_check') or len(self) != 1:
            return super().button_confirm()

        issues_html = self._check_cee_data_completeness()
        if not issues_html:
            return super().button_confirm()

        wizard = self.env['ibatix.wizard.cee.manquants'].create({
            'sale_order_id': self.id,
            'message_html': issues_html,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Données CEE manquantes',
            'res_model': 'ibatix.wizard.cee.manquants',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_select_cee_operation(self):
        self.ensure_one()
        wizard = self.env['ibatix.wizard.select.operation.cee'].create({'order_id': self.id})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Ajouter une opération CEE',
            'res_model': 'ibatix.wizard.select.operation.cee',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_recalculer_prime_cee(self):
        self.ensure_one()
        cee_lines = self.order_line.filtered('operation_cee_id')
        if not cee_lines:
            return
        if len(cee_lines) == 1:
            return cee_lines.action_ouvrir_wizard_cee()
        # Plusieurs lignes CEE : ouvre le wizard de sélection en mode recalcul
        wizard = self.env['ibatix.wizard.select.operation.cee'].create({'order_id': self.id})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Recalculer une prime CEE',
            'res_model': 'ibatix.wizard.select.operation.cee',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'recalcul_mode': True},
        }
