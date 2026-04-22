import json
import re
import urllib.request

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
    type_application_pac_cee = fields.Selection([
        ('basse_temperature', 'Basse température (35°C — plancher/plafond/ventiloconvecteur)'),
        ('haute_temperature', 'Moyenne/haute température (55°C — radiateurs)'),
    ], string='Application PAC')
    usage_pac_cee = fields.Selection([
        ('chauffage', 'Chauffage seul'),
        ('chauffage_ecs', 'Chauffage + eau chaude sanitaire'),
    ], string='Usage PAC')
    classe_regulateur_cee = fields.Selection([
        ('IV', 'Classe IV'), ('V', 'Classe V'), ('VI', 'Classe VI'),
        ('VII', 'Classe VII'), ('VIII', 'Classe VIII'),
    ], string='Classe du régulateur')
    classe_regulation_iso52120_cee = fields.Selection([
        ('a', 'Classe A (NF EN ISO 52120-1)'),
        ('b', 'Classe B (NF EN ISO 52120-1)'),
    ], string='Classe de régulation (ISO 52120-1)')
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

    @staticmethod
    def _desc_texte(product):
        """Retourne le texte brut du descriptif produit, en décodant le JSON si nécessaire."""
        raw = product.description_sale or ''
        if raw and raw.strip().startswith('{'):
            try:
                parsed = json.loads(raw)
                raw = parsed.get('en_US') or next(iter(parsed.values()), raw)
            except Exception:
                pass
        desc2 = product.description or ''
        if desc2 and desc2.strip().startswith('{'):
            try:
                parsed = json.loads(desc2)
                desc2 = parsed.get('en_US') or next(iter(parsed.values()), desc2)
            except Exception:
                pass
        return '\n'.join(filter(None, [product.name or '', raw, desc2]))

    def _extraire_donnees_produit(self, product_line):
        """Parse le descriptif du produit et extrait les données techniques CEE."""
        if not product_line or not product_line.product_id:
            return {}

        product = product_line.product_id
        desc = self._desc_texte(product)

        result = {}

        if product.name:
            result['marque'] = product.name.split()[0]

        if product.default_code:
            result['modele'] = product.default_code
        else:
            m = re.search(
                r'[Rr]éférence\s*(?:unité\s*extérieure|module\s*hydraulique|ext\.?)?\s*[:·]\s*([A-Z0-9][A-Z0-9\-\.\/\+\s]{2,30})',
                desc,
            )
            if m:
                result['modele'] = m.group(1).strip()

        m = re.search(r'COP\s*(?:nominal|chauffage)?\s*\(?[A-Z0-9/,\s]*\)?\s*[:·]\s*([\d]+[,\.][\d]+)', desc)
        if m:
            result['cop'] = float(m.group(1).replace(',', '.'))

        # SCOP à 35°C — format "ηs / SCOP à 35°C : 179 % / 4,56" ou "SCOP chauffage 35°C : 4,56"
        m = re.search(r'SCOP\s*(?:chauffage\s*)?(?:35[°º]C\s*)?[:·]\s*([\d]+[,\.][\d]+)', desc)
        if not m:
            m = re.search(r'ηs\s*/\s*SCOP\s*[àa]\s*35[°º]C\s*[:·]\s*[\d]+\s*%\s*/\s*([\d]+[,\.][\d]+)', desc)
        if m:
            result['scop'] = float(m.group(1).replace(',', '.'))

        # ηs (ETAS) — supporte "ETAS chauffage (ηs) 35°C : 189 %" et "ηs / SCOP à 35°C : 179 %"
        m = re.search(r'ETAS\s+chauffage[^:]*?35[°º]C\s*[:·]\s*([\d]+)\s*%', desc)
        if not m:
            m = re.search(r'(?:ETAS|ηs)\s*(?:chauffage\s*)?\(?ηs\)?\s*(?:35[°º]C\s*)?[:·]\s*([\d]+)\s*%', desc)
        if not m:
            m = re.search(r'Rendement\s*saisonnier\s*ηs\s*/\s*SCOP\s*[àa]\s*35[°º]C\s*[:·]\s*([\d]+)\s*%', desc)
        if not m:
            m = re.search(r'ηs\s*/\s*SCOP\s*[àa]\s*35[°º]C\s*[:·]\s*([\d]+)\s*%', desc)
        if m:
            result['etas'] = float(m.group(1))

        m = re.search(
            r'[Pp]uissance\s*(?:calorifique\s*)?(?:nominale\s*)?(?:\([^)]*\)\s*)?[:·]\s*([\d]+[,\.]?[\d]*)\s*kW',
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

        # PAC-specific fields
        if re.search(r'[Aa]pplication\s*[:·]\s*[Hh]aute\s*temp', desc) or \
                re.search(r'[Rr]adiateurs?\s*(?:haute\s*temp|existants)', desc):
            result['type_application_pac'] = 'haute_temperature'
        elif re.search(r'[Aa]pplication\s*[:·]\s*[Bb]asse\s*temp', desc) or \
                re.search(r'plancher\s*chauffant|ventiloconvecteur|35[°º]C', desc):
            result['type_application_pac'] = 'basse_temperature'

        if re.search(r'[Uu]sage\s*[:·]\s*[Cc]hauffage\s+seul', desc):
            result['usage_pac'] = 'chauffage'
        elif re.search(r'[Uu]sage\s*[:·].*(?:ECS|eau\s*chaude)', desc):
            result['usage_pac'] = 'chauffage_ecs'

        m = re.search(r'[Cc]lasse\s*du\s*r[ée]gulateur\s*[:·]\s*(VIII|VII|VI|IV|V)', desc)
        if m:
            result['classe_regulateur'] = m.group(1)

        return result

    # Libellés lisibles pour les champs produit manquants
    _LABELS_CHAMPS_PRODUIT = {
        'marque': 'Marque',
        'modele': 'Modèle / Référence',
        'etas': 'Efficacité ηs (%)',
        'puissance_kw': 'Puissance (kW)',
        'cop': 'COP',
        'scop': 'SCOP',
        'type_application_pac': 'Application PAC (BT / MT-HT)',
        'usage_pac': 'Usage PAC (chauffage / + ECS)',
        'classe_regulateur': 'Classe du régulateur',
        'classe_regulation_iso52120': 'Classe de régulation ISO 52120-1 (A ou B)',
    }

    def _champs_produit_requis(self):
        """Retourne la liste des champs produit attendus pour cette opération."""
        op = self.operation_cee_id
        champs_requis = (op.champs_requis or '') if op else ''
        requis = ['marque', 'modele']
        if 'etas' in champs_requis:
            requis.append('etas')
        if 'puissance_kw' in champs_requis:
            requis.append('puissance_kw')
        if 'cop' in champs_requis:
            requis.extend(['cop', 'scop'])
        if op and op.code == 'BAR-TH-171':
            requis.extend(['type_application_pac', 'usage_pac', 'classe_regulateur'])
        if op and op.code == 'BAR-TH-173':
            requis.extend(['surface_chauffee', 'type_logement', 'classe_regulation_iso52120'])
        return requis

    def _extraire_donnees_produit_ia(self, product_line, api_key):
        """Extrait les données techniques via Claude depuis le descriptif produit.
        Retourne (dict_valeurs, liste_champs_manquants).
        """
        if not product_line or not product_line.product_id:
            return {}, self._champs_produit_requis()

        product = product_line.product_id
        desc = self._desc_texte(product)
        if product_line.name and product_line.name != product.name:
            desc = product_line.name + '\n' + desc

        if not desc.strip():
            return {}, self._champs_produit_requis()

        prompt = (
            "Tu es un expert en equipements CEE (chauffage, regulation, isolation). "
            "Extrait les donnees techniques du descriptif produit suivant.\n\n"
            f"Descriptif :\n{desc}\n\n"
            "Retourne UNIQUEMENT un JSON valide avec ces cles (null si non trouve) :\n"
            '{\n'
            '  "marque": "string ou null",\n'
            '  "modele": "string ou null",\n'
            '  "etas": entier (%) ou null,\n'
            '  "puissance_kw": decimal ou null,\n'
            '  "cop": decimal ou null,\n'
            '  "scop": decimal ou null,\n'
            '  "type_application_pac": "basse_temperature" ou "haute_temperature" ou null,\n'
            '  "usage_pac": "chauffage" ou "chauffage_ecs" ou null,\n'
            '  "classe_regulateur": "IV" ou "V" ou "VI" ou "VII" ou "VIII" ou null,\n'
            '  "classe_regulation_iso52120": "a" ou "b" ou null\n'
            '}\n\n'
            "Regles d'extraction :\n"
            "- etas : rendement saisonnier en chauffage (note ηs ou ETAS), a 35°C si disponible,"
            " retourner uniquement le nombre entier en % (ex: 179 pour 179 %)\n"
            "- type_application_pac : haute_temperature si radiateurs / haute temperature / 55°C / 60°C;"
            " basse_temperature si plancher chauffant / ventiloconvecteur / 35°C\n"
            "- usage_pac : chauffage si chauffage seul, chauffage_ecs si chauffage + ECS ou eau chaude sanitaire\n"
            "- classe_regulateur : chiffre romain IV a VIII, chercher 'Classe du regulateur'\n"
            "- classe_regulation_iso52120 : classe de regulation NF EN ISO 52120-1 ;"
            " retourner 'a' si Classe A, 'b' si Classe B\n"
            "- marque : fabricant (ex: Mitsubishi, Atlantic, Netatmo, Delta Dore...)\n"
            "- modele : reference commerciale principale de l'equipement\n"
            "- cop : COP nominal (A7/W35), nombre decimal\n"
            "- scop : SCOP a 35°C, nombre decimal\n"
            "Reponds uniquement en JSON, sans markdown, sans commentaire."
        )

        payload = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 512,
            "messages": [{"role": "user", "content": prompt}],
        }
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=data,
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode('utf-8'))
            raw = body.get('content', [{}])[0].get('text', '').strip()
            extracted = json.loads(raw)
        except Exception:
            extracted = None

        if extracted is None:
            result = self._extraire_donnees_produit(product_line)
        else:
            result = {}
            for key in ('marque', 'modele', 'etas', 'puissance_kw', 'cop', 'scop',
                        'type_application_pac', 'usage_pac', 'classe_regulateur',
                        'classe_regulation_iso52120'):
                val = extracted.get(key)
                if val is not None:
                    # Normalise la classe ISO 52120 en minuscule ('A'/'B' → 'a'/'b')
                    if key == 'classe_regulation_iso52120' and isinstance(val, str):
                        val = val.strip().lower()
                        if val not in ('a', 'b'):
                            val = None
                    if val is not None:
                        result[key] = val

        requis = self._champs_produit_requis()
        missing = [f for f in requis if not result.get(f)]
        return result, missing

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
                classe_regulation_iso52120=self.classe_regulation_iso52120_cee or '',
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
            'type_application_pac': self.type_application_pac_cee or False,
            'usage_pac': self.usage_pac_cee or False,
            'classe_regulateur': self.classe_regulateur_cee or False,
            'classe_regulation_iso52120': self.classe_regulation_iso52120_cee or False,
            'notes_techniques': self.notes_techniques_cee or '',
            'guide_technique': guide_html,
            'fiche_analysee': fiche_deja_analysee,
        }

        # ── Auto-extraction depuis le produit suivant ────────────────────────
        champs_manquants = ''
        if next_line:
            api_key = self.env['ir.config_parameter'].sudo().get_param(
                'ibatix.anthropic_api_key', ''
            )
            if api_key:
                extracted, missing = self._extraire_donnees_produit_ia(next_line, api_key)
            else:
                extracted = self._extraire_donnees_produit(next_line)
                missing = []

            for key, val in extracted.items():
                if val and not wizard_vals.get(key):
                    wizard_vals[key] = val

            # Champs manquants = requis mais absents même après extraction ET non déjà sauvegardés
            labels = self._LABELS_CHAMPS_PRODUIT
            manquants_filtrés = [
                labels.get(f, f) for f in missing if not wizard_vals.get(f)
            ]
            if manquants_filtrés:
                champs_manquants = ', '.join(manquants_filtrés)

        wizard_vals['champs_manquants_produit'] = champs_manquants
        wizard_vals['product_line_id'] = next_line.id if next_line else False

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
