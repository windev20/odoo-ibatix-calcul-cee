import re

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

    # Champ non-stocké : ID du wizard BAR-TH-171 à ouvrir (consommé côté JS)
    barth171_wizard_id = fields.Char(store=False, default='')

    # ── Lien opération CEE (direct — fonctionne sur lignes note ET produit) ──
    operation_cee_id = fields.Many2one(
        'ibatix.operation.cee',
        string='Opération CEE',
        store=True,
        ondelete='set null',
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
    profil_soutirage_cee = fields.Selection([
        ('M', 'M'), ('L', 'L'), ('XL', 'XL'),
    ], string='Profil de soutirage')
    efficacite_energetique_cee = fields.Float(string='Efficacité énergétique (%)', digits=(10, 1))
    notes_techniques_cee = fields.Text(string='Notes complémentaires')

    def _get_next_product_line(self):
        """Retourne la ligne produit ordinaire qui suit immédiatement cette ligne CEE."""
        self.ensure_one()
        sorted_lines = self.order_id.order_line.sorted(lambda l: (l.sequence, l.id))
        found = False
        for line in sorted_lines:
            if found and line.product_id and not line.display_type:
                return line
            if line.id == self.id:
                found = True
        return None

    def _extraire_donnees_produit(self, product_line):
        """Parse le descriptif du produit et extrait les données techniques CEE."""
        if not product_line or not product_line.product_id:
            return {}

        product = product_line.product_id
        desc = '\n'.join(filter(None, [
            product.name or '',
            product.description_sale or '',
            product.description or '',
        ]))

        result = {}

        if product.name:
            result['marque'] = product.name.split()[0]

        if product.default_code:
            result['modele'] = product.default_code
        else:
            m = re.search(
                r'[Rr]éférence\s*(?:unité\s*extérieure|ext\.?)?\s*[:·]\s*([A-Z0-9][A-Z0-9\-\.\/]+)',
                desc,
            )
            if m:
                result['modele'] = m.group(1)

        m = re.search(r'COP\s*(?:nominal|chauffage)?\s*[:·]\s*([\d]+[,\.][\d]+)', desc)
        if m:
            result['cop'] = float(m.group(1).replace(',', '.'))

        m = re.search(r'SCOP\s*(?:chauffage\s*)?(?:35[°º]C\s*)?[:·]\s*([\d]+[,\.][\d]+)', desc)
        if m:
            result['scop'] = float(m.group(1).replace(',', '.'))

        m = re.search(r'ETAS\s+chauffage[^:]*?35[°º]C\s*[:·]\s*([\d]+)\s*%', desc)
        if not m:
            m = re.search(r'(?:ETAS|ηs)\s*(?:chauffage)?\s*[:·]\s*([\d]+)\s*%', desc)
        if m:
            result['etas'] = float(m.group(1))

        m = re.search(
            r'[Pp]uissance\s*(?:calorifique\s*)?(?:nominale\s*)?[:·]\s*([\d]+[,\.]?[\d]*)\s*kW',
            desc,
        )
        if not m:
            m = re.search(r'([\d]+[,\.]?[\d]*)\s*kW', product.name or '')
        if m:
            result['puissance_kw'] = float(m.group(1).replace(',', '.'))

        m = re.search(r'[Rr]ésistance\s*thermique\s*R[^:]*[:·]\s*([\d]+[,\.]?[\d]*)', desc)
        if m:
            result['resistance_thermique'] = float(m.group(1).replace(',', '.'))

        m = re.search(r'[Ss]urface\s*\(m[²2]\)\s*[:·]\s*([\d]+[,\.]?[\d]*)', desc)
        if m:
            result['surface_m2'] = float(m.group(1).replace(',', '.'))

        if re.search(r'[Mm]aison\s*individuelle', desc):
            result['type_logement'] = 'maison'
        elif re.search(r'[Aa]ppartement', desc):
            result['type_logement'] = 'appartement'

        m = re.search(r'[Ee]fficacité\s*[Ee]nergétique\s*[:·]\s*([\d]+[,\.]?[\d]*)\s*%', desc)
        if m:
            result['efficacite_energetique'] = float(m.group(1).replace(',', '.'))

        return result

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

        # ── Ligne produit suivante (pour qty et extraction technique) ─────────
        next_line = self._get_next_product_line()

        # ── Surface : valeur saisie → quantité ligne suivante → 0 ────────────
        surface = self.surface_m2_cee or (next_line.product_uom_qty if next_line else 0.0)

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
                profil_soutirage=self.profil_soutirage_cee or '',
                efficacite_energetique=self.efficacite_energetique_cee,
            )

        # ── Guide technique déjà analysé ? ──────────────────────────────────
        guide_html = (op.guide_html or '') if op else ''
        fiche_deja_analysee = bool(guide_html or (op and op.formule_analysee))

        # ── Données de base (valeurs sauvegardées) ───────────────────────────
        wizard_vals = {
            'sale_line_id': self.id,
            'cumac_cee': cumac_init,
            'valo_cee': valo,
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
            'profil_soutirage': self.profil_soutirage_cee or False,
            'efficacite_energetique': self.efficacite_energetique_cee,
            'notes_techniques': self.notes_techniques_cee or '',
            'guide_technique': guide_html,
            'fiche_analysee': fiche_deja_analysee,
        }

        # ── Auto-extraction depuis le produit suivant ────────────────────────
        if next_line:
            extracted = self._extraire_donnees_produit(next_line)
            for key, val in extracted.items():
                if val:
                    wizard_vals[key] = val

        wizard = self.env['ibatix.wizard.cee'].create(wizard_vals)

        return {
            'type': 'ir.actions.act_window',
            'name': f"Prime CEE — {op.display_name if op else ''}",
            'res_model': 'ibatix.wizard.cee',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @api.onchange('operation_cee_id')
    def _onchange_operation_cee_note(self):
        """Sur une ligne note : remplit le nom avec le code + libellé de l'opération."""
        if self.display_type == 'line_note' and self.operation_cee_id:
            op = self.operation_cee_id
            self.name = f"{op.code} — {op.name}" if op.code else op.name

    @api.onchange('product_id')
    def _onchange_product_barth171_popup(self):
        self.barth171_wizard_id = ''
        if not self.product_id:
            self.operation_cee_id = False
            return
        # Synchronise operation_cee_id depuis le produit (lignes produit)
        self.operation_cee_id = self.product_id.product_tmpl_id.operation_cee_id
        op = self.operation_cee_id
        if not op or op.code != 'BAR-TH-171':
            return
        if self.surface_chauffee_cee and self.type_logement_cee:
            return
        order_id = self.order_id._origin.id or self.order_id.id
        if not order_id:
            return
        wizard = self.env['ibatix.wizard.barth171'].create({
            'order_id': order_id,
            'product_id': self.product_id.id,
        })
        self.barth171_wizard_id = str(wizard.id)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            order = rec.order_id
            if (rec.operation_cee_id and rec.operation_cee_id.code == 'BAR-TH-171'
                    and not rec.surface_chauffee_cee
                    and order.barth171_product_pending == rec.product_id.id
                    and order.barth171_surface_pending):
                rec.write({
                    'surface_chauffee_cee': order.barth171_surface_pending,
                    'type_logement_cee': order.barth171_type_pending or False,
                    'type_energie_cee': order.barth171_energie_pending or False,
                })
                order.write({
                    'barth171_surface_pending': 0.0,
                    'barth171_type_pending': '',
                    'barth171_energie_pending': '',
                    'barth171_product_pending': 0,
                })
        return records

    def action_open_select_cee_operation(self):
        order_id = self.env.context.get('order_id') or (self.order_id.id if self else False)
        if not order_id:
            return
        wizard = self.env['ibatix.wizard.select.operation.cee'].create({'order_id': order_id})
        return {
            'type': 'ir.actions.act_window',
            'name': 'Ajouter une opération CEE',
            'res_model': 'ibatix.wizard.select.operation.cee',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ── Type de ligne CEE (ni produit, ni note, ni section) ──────────────────
    display_type = fields.Selection(
        selection_add=[('line_cee', 'Opération CEE')],
        ondelete={'line_cee': 'cascade'},
    )


    # -- Champs MaPrimeRenov' ------------------------------------------------
    prime_mpr = fields.Float(string='Prime MPR (EUR)', digits=(10, 2), default=0.0)
    prime_mpr_ecrete = fields.Boolean(string='Ecretement applique', default=False)

    def _calculer_prime_mpr(self):
        self.ensure_one()
        op = self.operation_cee_id
        if not op or not op.eligible_mpr:
            self.prime_mpr = 0.0
            self.prime_mpr_ecrete = False
            return

        categorie = self.order_id.partner_id.categorie_precarite

        if categorie == 'precaire':
            taux = 0.90
            forfait_unitaire = op.prime_mpr_bleu
        elif categorie == 'modeste':
            taux = 0.75
            forfait_unitaire = op.prime_mpr_jaune
        elif categorie == 'intermediaire':
            taux = 0.60
            forfait_unitaire = op.prime_mpr_violet
        else:
            self.prime_mpr = 0.0
            self.prime_mpr_ecrete = False
            return

        if not forfait_unitaire:
            self.prime_mpr = 0.0
            self.prime_mpr_ecrete = False
            return

        next_line = self._get_next_product_line()

        if op.type_calcul_mpr == 'par_m2':
            surface = self.surface_m2_cee or self.surface_chauffee_cee or 0.0
            forfait = forfait_unitaire * surface
        elif op.type_calcul_mpr == 'par_unite':
            qty = next_line.product_uom_qty if next_line else 1.0
            forfait = forfait_unitaire * qty
        else:
            forfait = forfait_unitaire

        if not forfait:
            self.prime_mpr = 0.0
            self.prime_mpr_ecrete = False
            return

        ecrete = False
        plafond = op.plafond_depense_mpr
        if plafond:
            depense = next_line.price_total if next_line else 0.0
            depense_eligible = min(depense, plafond)
            plafond_ecretement = max(0.0, taux * depense_eligible - (self.prime_cee or 0.0))
            if forfait > plafond_ecretement:
                forfait = plafond_ecretement
                ecrete = True

        self.prime_mpr = round(forfait, 2)
        self.prime_mpr_ecrete = ecrete
