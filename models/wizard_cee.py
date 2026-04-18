import base64
import json
import logging
import urllib.error
import urllib.request

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


def _appel_claude_analyse_complete(pdf_bytes, api_key, operation_code, operation_name):
    """
    Analyse complète de la fiche PDF CEE via Claude :
    - Guide technique HTML pour l'installateur
    - Champs requis pour cette opération
    - Formule de calcul Cumac en Python

    Retourne un dict :
    {
        'guide_html': str,
        'champs_requis': str,          # ex : "surface_m2,resistance_thermique"
        'formule_cumac_python': str,   # ex : "surface_m2 * resistance_thermique * 36.5"
        'formule_description': str,
    }
    """
    pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')

    champs_disponibles = (
        "surface_m2 (surface en m²), "
        "resistance_thermique (résistance thermique R en m².K/W), "
        "puissance_kw (puissance nominale en kW), "
        "cop (COP), "
        "scop (SCOP), "
        "etas (efficacité saisonnière ηs en %), "
        "nb_logements (nombre de logements)"
    )

    prompt = (
        f"Tu es un expert CEE français. Opération : {operation_code} — {operation_name}.\n\n"
        f"Variables disponibles dans notre logiciel : {champs_disponibles}\n\n"
        "Analyse cette fiche CEE et retourne UN SEUL objet JSON valide (sans markdown ni balises), "
        "avec exactement ces 4 clés :\n"
        "{\n"
        '  "guide_html": "<h4>...</h4>...",\n'
        '  "champs_requis": "var1,var2",\n'
        '  "formule_cumac_python": "expression Python",\n'
        '  "formule_description": "description lisible"\n'
        "}\n\n"
        "Règles :\n"
        "- guide_html : HTML compact (<h4>,<ul>,<li>,<strong>) listant conditions d'éligibilité, "
        "données techniques à collecter, documents justificatifs. En français. Sans CSS.\n"
        "- champs_requis : UNIQUEMENT les variables ci-dessus nécessaires au calcul, séparées par virgule.\n"
        "- formule_cumac_python : expression Python évaluable utilisant ces variables. "
        "Intègre les constantes directement (durée de vie, facteur zone H2 si applicable). "
        "Exemple : surface_m2 * resistance_thermique * 36.5\n"
        "- formule_description : formule lisible pour l'utilisateur.\n"
        "Réponds uniquement en JSON."
    )

    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2048,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=data,
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'anthropic-beta': 'pdfs-2024-09-25',
            'content-type': 'application/json',
        },
        method='POST',
    )

    empty = {'guide_html': '', 'champs_requis': '', 'formule_cumac_python': '', 'formule_description': ''}

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode('utf-8'))
        raw = body.get('content', [{}])[0].get('text', '').strip()

        # Nettoyer les blocs markdown éventuels
        if raw.startswith('```'):
            lines = raw.splitlines()
            raw = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])

        result = json.loads(raw)
        return {
            'guide_html': result.get('guide_html', ''),
            'champs_requis': result.get('champs_requis', ''),
            'formule_cumac_python': result.get('formule_cumac_python', ''),
            'formule_description': result.get('formule_description', ''),
        }
    except json.JSONDecodeError as e:
        _logger.error("Claude : réponse JSON invalide — %s\nRaw: %s", e, raw[:500])
        return empty
    except urllib.error.HTTPError as e:
        _logger.error("Claude API erreur %s : %s", e.code, e.read().decode())
        return empty
    except Exception as e:
        _logger.error("Claude API exception : %s", e)
        return empty


def _evaluer_cumac(formule, surface_m2, resistance_thermique, puissance_kw,
                   cop, scop, etas, nb_logements):
    """Évalue la formule Python de cumac dans un contexte sécurisé."""
    if not formule:
        return 0.0
    ctx = {
        'surface_m2': surface_m2 or 0.0,
        'resistance_thermique': resistance_thermique or 0.0,
        'puissance_kw': puissance_kw or 0.0,
        'cop': cop or 0.0,
        'scop': scop or 0.0,
        'etas': etas or 0.0,
        'nb_logements': nb_logements or 0,
        'max': max,
        'min': min,
        'round': round,
    }
    try:
        return float(eval(formule, {"__builtins__": {}}, ctx))  # noqa: S307
    except Exception as e:
        _logger.warning("Erreur évaluation formule cumac '%s': %s", formule, e)
        return 0.0


class WizardCee(models.TransientModel):
    _name = 'ibatix.wizard.cee'
    _description = "Calcul de la prime CEE"

    # ── Contexte (lecture seule) ─────────────────────────────────────────────
    sale_line_id = fields.Many2one(
        'sale.order.line',
        required=True,
        readonly=True,
    )
    operation_cee_id = fields.Many2one(
        'ibatix.operation.cee',
        related='sale_line_id.operation_cee_id',
        string='Opération CEE',
        readonly=True,
    )
    delegataire_id = fields.Many2one(
        'ibatix.delegataire.cee',
        related='sale_line_id.order_id.delegataire_cee_id',
        string='Délégataire',
        readonly=True,
    )
    contrat_id = fields.Many2one(
        'ibatix.delegataire.contrat',
        related='sale_line_id.order_id.contrat_cee_id',
        string='Contrat en cours',
        readonly=True,
    )
    categorie_precarite = fields.Selection(
        related='sale_line_id.order_id.partner_id.categorie_precarite',
        string='Précarité client',
        readonly=True,
    )
    nom_client = fields.Char(
        related='sale_line_id.order_id.partner_id.name',
        string='Client',
        readonly=True,
    )

    # ── Métadonnées de la formule (depuis l'opération) ───────────────────────
    champs_requis = fields.Char(
        related='operation_cee_id.champs_requis',
        string='Champs requis',
        readonly=True,
    )
    formule_cumac_python = fields.Text(
        related='operation_cee_id.formule_cumac_python',
        string='Formule Cumac',
        readonly=True,
    )
    formule_description = fields.Char(
        related='operation_cee_id.formule_description',
        string='Description formule',
        readonly=True,
    )

    # ── Guide technique (extrait par Claude) ────────────────────────────────
    guide_technique = fields.Html(
        string='Guide technique',
        readonly=True,
        sanitize=False,
    )
    fiche_analysee = fields.Boolean(default=False)

    # ── Paramètres techniques (saisis par l'utilisateur) ────────────────────
    marque = fields.Char(string='Marque')
    modele = fields.Char(string='Modèle / Référence')
    surface_m2 = fields.Float(string='Surface (m²)', digits=(10, 2))
    puissance_kw = fields.Float(string='Puissance (kW)', digits=(10, 2))
    cop = fields.Float(string='COP', digits=(10, 2))
    scop = fields.Float(string='SCOP', digits=(10, 2))
    etas = fields.Float(string='ηs (%)', digits=(10, 1))
    resistance_thermique = fields.Float(string='Résistance thermique R (m².K/W)', digits=(10, 2))
    nb_logements = fields.Integer(string='Nombre de logements')
    type_energie = fields.Selection([
        ('electricite', 'Électricité'),
        ('gaz', 'Gaz naturel'),
        ('fioul', 'Fioul'),
        ('bois', 'Bois / Biomasse'),
        ('autre', 'Autre'),
    ], string="Énergie de chauffage avant travaux")
    notes_techniques = fields.Text(string='Notes complémentaires')

    # ── Calcul de la prime ───────────────────────────────────────────────────
    cumac_cee = fields.Float(
        string='Cumac retenu (MWhc)',
        digits=(10, 3),
    )
    valo_cee = fields.Float(
        string='Valorisation (€/MWhc)',
        digits=(10, 4),
    )
    prime_cee = fields.Float(
        string='Prime CEE calculée (€)',
        compute='_compute_prime_cee',
        digits=(10, 2),
    )

    @api.depends('cumac_cee', 'valo_cee')
    def _compute_prime_cee(self):
        for rec in self:
            # cumac en kWhc, valo en €/MWhc → division par 1000 pour obtenir des €
            rec.prime_cee = rec.cumac_cee * rec.valo_cee / 1000

    # ── Recalcul automatique du cumac quand les paramètres changent ──────────

    @api.onchange('surface_m2', 'resistance_thermique', 'puissance_kw',
                  'cop', 'scop', 'etas', 'nb_logements')
    def _onchange_params_techniques(self):
        """Recalcule le cumac automatiquement si la formule est disponible."""
        formule = self.operation_cee_id.formule_cumac_python if self.operation_cee_id else ''
        if not formule:
            return
        self.cumac_cee = _evaluer_cumac(
            formule,
            self.surface_m2,
            self.resistance_thermique,
            self.puissance_kw,
            self.cop,
            self.scop,
            self.etas,
            self.nb_logements,
        )

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_analyser_fiche(self):
        """Appelle Claude pour analyser la fiche PDF : guide + formule + champs requis."""
        self.ensure_one()
        op = self.operation_cee_id
        if not op or not op.fiche_pdf:
            self.guide_technique = (
                "<p><em>Aucune fiche PDF renseignée sur cette opération CEE. "
                "Ajoutez-la dans la configuration des opérations CEE.</em></p>"
            )
            self.fiche_analysee = True
            return self._reopen()

        api_key = self.env['ir.config_parameter'].sudo().get_param(
            'ibatix.anthropic_api_key', ''
        )
        if not api_key:
            self.guide_technique = (
                "<p><strong>Clé API Anthropic non configurée.</strong> "
                "Ajoutez le paramètre <code>ibatix.anthropic_api_key</code> "
                "dans Paramètres › Technique › Paramètres système.</p>"
            )
            self.fiche_analysee = True
            return self._reopen()

        pdf_bytes = base64.b64decode(op.fiche_pdf)
        result = _appel_claude_analyse_complete(
            pdf_bytes, api_key, op.code or '', op.name or ''
        )

        # Stocker le guide sur le wizard (transient)
        self.guide_technique = result['guide_html'] or (
            "<p><em>L'analyse n'a pas retourné de résultat. "
            "Vérifiez les logs serveur.</em></p>"
        )
        self.fiche_analysee = True

        # Stocker la formule et les champs sur l'opération (persistant)
        if result['formule_cumac_python']:
            op.sudo().write({
                'champs_requis': result['champs_requis'],
                'formule_cumac_python': result['formule_cumac_python'],
                'formule_description': result['formule_description'],
                'formule_analysee': True,
            })
            # Recalculer immédiatement le cumac avec les valeurs déjà saisies
            self.cumac_cee = _evaluer_cumac(
                result['formule_cumac_python'],
                self.surface_m2,
                self.resistance_thermique,
                self.puissance_kw,
                self.cop,
                self.scop,
                self.etas,
                self.nb_logements,
            )

        return self._reopen()

    def action_confirmer(self):
        """Enregistre la prime et les paramètres techniques sur la ligne de devis."""
        self.ensure_one()
        params = self._build_params_text()
        self.sale_line_id.write({
            'prime_cee': self.prime_cee,
            'cumac_cee': self.cumac_cee,
            'valo_cee': self.valo_cee,
            'params_techniques_cee': params,
        })
        return {'type': 'ir.actions.act_window_close'}

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _reopen(self):
        """Retourne une action pour rouvrir ce wizard (après mise à jour d'un champ)."""
        return {
            'type': 'ir.actions.act_window',
            'name': f"Prime CEE — {self.operation_cee_id.display_name or ''}",
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _build_params_text(self):
        """Construit un résumé textuel des paramètres techniques saisis."""
        lines = []
        if self.marque:
            lines.append(f"Marque : {self.marque}")
        if self.modele:
            lines.append(f"Modèle : {self.modele}")
        if self.surface_m2:
            lines.append(f"Surface : {self.surface_m2} m²")
        if self.puissance_kw:
            lines.append(f"Puissance : {self.puissance_kw} kW")
        if self.cop:
            lines.append(f"COP : {self.cop}")
        if self.scop:
            lines.append(f"SCOP : {self.scop}")
        if self.etas:
            lines.append(f"ηs : {self.etas} %")
        if self.resistance_thermique:
            lines.append(f"R : {self.resistance_thermique} m².K/W")
        if self.nb_logements:
            lines.append(f"Nb logements : {self.nb_logements}")
        if self.type_energie:
            labels = dict(self._fields['type_energie'].selection)
            lines.append(f"Énergie remplacée : {labels.get(self.type_energie, self.type_energie)}")
        if self.notes_techniques:
            lines.append(f"Notes : {self.notes_techniques}")
        return '\n'.join(lines)
