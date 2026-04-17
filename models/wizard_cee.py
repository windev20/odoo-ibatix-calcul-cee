import base64
import json
import logging
import urllib.error
import urllib.request

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


def _appel_claude_fiche(pdf_bytes, api_key, operation_code, operation_name):
    """
    Envoie la fiche PDF de l'operation CEE a Claude et retourne un guide
    HTML expliquant les informations techniques a collecter.
    """
    pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')

    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
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
                    {
                        "type": "text",
                        "text": (
                            f"Tu es un expert en certificats d'economies d'energie (CEE) francais.\n"
                            f"Voici la fiche standardisee de l'operation CEE : {operation_code} — {operation_name}.\n\n"
                            "Analyse cette fiche et retourne un guide HTML COMPACT (sans CSS externe) "
                            "qui liste UNIQUEMENT :\n"
                            "1. Les conditions d'eligibilite essentielles a verifier\n"
                            "2. Les informations techniques obligatoires a collecter sur le chantier "
                            "(marque, modele, puissance, surface, COP, etc.)\n"
                            "3. Les documents justificatifs a fournir\n\n"
                            "Format : HTML simple avec <h4>, <ul>, <li>, <strong>. "
                            "Sois concis et pratique pour un installateur sur le terrain. "
                            "Reponds en francais."
                        ),
                    },
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

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode('utf-8'))
        html = body.get('content', [{}])[0].get('text', '').strip()
        # Nettoyer les blocs markdown eventuels
        if html.startswith('```'):
            lines = html.splitlines()
            html = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])
        return html
    except urllib.error.HTTPError as e:
        _logger.error("Claude API erreur %s : %s", e.code, e.read().decode())
        return ''
    except Exception as e:
        _logger.error("Claude API exception : %s", e)
        return ''


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
            rec.prime_cee = rec.cumac_cee * rec.valo_cee

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_analyser_fiche(self):
        """Appelle Claude pour analyser la fiche PDF de l'opération CEE."""
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
        html = _appel_claude_fiche(pdf_bytes, api_key, op.code or '', op.name or '')

        self.guide_technique = html or (
            "<p><em>L'analyse de la fiche n'a pas retourné de résultat. "
            "Vérifiez les logs serveur.</em></p>"
        )
        self.fiche_analysee = True
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
