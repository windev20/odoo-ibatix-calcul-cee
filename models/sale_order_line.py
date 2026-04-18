from odoo import api, fields, models

# Mapping code département → zone climatique CEE (H1 / H2 / H3)
_DEPT_H1 = {
    '02', '03', '08', '10', '21', '25', '27', '28', '39', '41', '45',
    '51', '52', '54', '55', '57', '58', '59', '60', '62', '67', '68',
    '70', '71', '75', '76', '77', '78', '80', '88', '89', '90',
    '91', '92', '93', '94', '95',
}
_DEPT_H3 = {'06', '11', '13', '30', '34', '66', '83', '84'}


def _zone_from_zip(zip_code):
    if not zip_code or len(zip_code) < 2:
        return False
    dept = zip_code[:2].upper()
    if dept == '20' or zip_code[:3] in ('200', '201', '202'):
        return 'h3'  # Corse
    if dept in _DEPT_H1:
        return 'h1'
    if dept in _DEPT_H3:
        return 'h3'
    return 'h2'


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # ── Lien opération CEE ───────────────────────────────────────────────────
    operation_cee_id = fields.Many2one(
        'ibatix.operation.cee',
        related='product_id.product_tmpl_id.operation_cee_id',
        string='Opération CEE',
        store=True,
    )

    # ── Résultats du calcul ──────────────────────────────────────────────────
    prime_cee = fields.Float(string='Prime CEE (€)', digits=(10, 2), default=0.0)
    cumac_cee = fields.Float(string='Cumac (MWhc)', digits=(10, 3))
    valo_cee = fields.Float(string='Valorisation (€/MWhc)', digits=(10, 4))
    params_techniques_cee = fields.Text(string='Paramètres techniques CEE')

    # ── Paramètres techniques persistés ─────────────────────────────────────
    marque_cee = fields.Char(string='Marque')
    modele_cee = fields.Char(string='Modèle / Référence')
    surface_m2_cee = fields.Float(string='Surface (m²)', digits=(10, 2))
    surface_chauffee_cee = fields.Float(string='Surface chauffée (m²)', digits=(10, 2))
    resistance_thermique_cee = fields.Float(string='Résistance thermique R', digits=(10, 2))
    puissance_kw_cee = fields.Float(string='Puissance (kW)', digits=(10, 2))
    cop_cee = fields.Float(string='COP', digits=(10, 2))
    scop_cee = fields.Float(string='SCOP', digits=(10, 2))
    etas_cee = fields.Float(string='ηs (%)', digits=(10, 1))
    nb_logements_cee = fields.Integer(string='Nombre de logements')
    type_energie_cee = fields.Selection([
        ('electricite', 'Électricité'),
        ('gaz', 'Gaz naturel'),
        ('fioul', 'Fioul'),
        ('bois', 'Bois / Biomasse'),
        ('autre', 'Autre'),
    ], string='Énergie avant travaux')
    type_logement_cee = fields.Selection([
        ('maison', 'Maison individuelle'),
        ('appartement', 'Appartement'),
    ], string='Type de logement')
    zone_climatique_cee = fields.Selection([
        ('h1', 'Zone H1 (Nord / Est)'),
        ('h2', 'Zone H2 (Centre / Ouest)'),
        ('h3', 'Zone H3 (Méditerranée)'),
    ], string='Zone climatique')
    notes_techniques_cee = fields.Text(string='Notes complémentaires')

    def action_ouvrir_wizard_cee(self):
        """Ouvre le wizard de calcul de prime CEE pour cette ligne."""
        self.ensure_one()

        delegataire = self.order_id.delegataire_cee_id
        contrat = self.order_id.contrat_cee_id
        categorie = self.order_id.partner_id.categorie_precarite
        op = self.operation_cee_id

        # ── Valorisation depuis le contrat ───────────────────────────────────
        cumac_delegataire = 0.0
        valo = self.valo_cee or 0.0

        if delegataire and op:
            op_del = delegataire.operation_ids.filtered(
                lambda o: o.code == op.code
            )[:1]
            if op_del:
                if categorie in ('precaire', 'modeste'):
                    cumac_delegataire = op_del.cumac_precaire or op_del.cumac_total
                else:
                    cumac_delegataire = op_del.cumac_classique or op_del.cumac_total

        if not valo and contrat:
            if categorie in ('precaire', 'modeste'):
                valo = contrat.valo_precaire_client
            else:
                valo = contrat.valo_classique_client

        # ── Zone climatique depuis le code postal du client ──────────────────
        zone = self.zone_climatique_cee or _zone_from_zip(
            self.order_id.partner_id.zip or ''
        ) or False

        # ── Surface = quantité si pas encore saisie ──────────────────────────
        surface = self.surface_m2_cee or self.product_uom_qty

        # ── Pré-calcul cumac si formule connue et pas encore calculé ─────────
        from .wizard_cee import _evaluer_cumac
        formule = op.formule_cumac_python if op else ''
        cumac_init = self.cumac_cee or cumac_delegataire
        if formule and not cumac_init:
            cumac_init = _evaluer_cumac(
                formule,
                surface_m2=surface,
                resistance_thermique=self.resistance_thermique_cee,
                puissance_kw=self.puissance_kw_cee,
                cop=self.cop_cee,
                scop=self.scop_cee,
                etas=self.etas_cee,
                nb_logements=self.nb_logements_cee,
                surface_chauffee=self.surface_chauffee_cee,
                type_logement=self.type_logement_cee or '',
                zone_climatique=zone or '',
            )

        # ── Guide technique déjà analysé ? ──────────────────────────────────
        guide_html = (op.guide_html or '') if op else ''
        fiche_deja_analysee = bool(guide_html or (op and op.formule_analysee))

        wizard = self.env['ibatix.wizard.cee'].create({
            'sale_line_id': self.id,
            'cumac_cee': cumac_init,
            'valo_cee': valo,
            # Paramètres techniques sauvegardés
            'marque': self.marque_cee or '',
            'modele': self.modele_cee or '',
            'surface_m2': surface,
            'surface_chauffee': self.surface_chauffee_cee,
            'resistance_thermique': self.resistance_thermique_cee,
            'puissance_kw': self.puissance_kw_cee,
            'cop': self.cop_cee,
            'scop': self.scop_cee,
            'etas': self.etas_cee,
            'nb_logements': self.nb_logements_cee,
            'type_energie': self.type_energie_cee or False,
            'type_logement': self.type_logement_cee or False,
            'zone_climatique': zone or False,
            'notes_techniques': self.notes_techniques_cee or '',
            'guide_technique': guide_html,
            'fiche_analysee': fiche_deja_analysee,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': f"Prime CEE — {op.display_name if op else ''}",
            'res_model': 'ibatix.wizard.cee',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
