import base64

from odoo import api, fields, models
from odoo.exceptions import UserError


class IbatixOperationCee(models.Model):
    _inherit = 'ibatix.operation.cee'

    # ── Résultats de l'analyse IA (stockés une fois pour toutes) ────────────
    champs_requis = fields.Char(
        string='Champs techniques requis',
        help="Noms des variables séparés par virgule : surface_m2,resistance_thermique,...",
    )
    formule_cumac_python = fields.Text(
        string='Formule Cumac (Python)',
        help="Expression Python évaluable. Variables : surface_m2, surface_chauffee, "
             "resistance_thermique, puissance_kw, cop, scop, etas, nb_logements, "
             "zone_climatique, facteur_zone, type_logement, facteur_logement.",
    )
    formule_description = fields.Char(
        string='Description de la formule',
    )
    formule_analysee = fields.Boolean(
        string='Formule analysée par l\'IA',
        default=False,
    )
    guide_html = fields.Html(
        string='Guide technique',
        sanitize=False,
        help="Guide généré par l'IA à partir de la fiche PDF.",
    )

    @api.onchange('fiche_pdf')
    def _onchange_fiche_pdf(self):
        """Quand le PDF est remplacé, invalide l'analyse précédente."""
        if self.fiche_pdf and self.formule_analysee:
            self.formule_analysee = False
            self.guide_html = False
            self.champs_requis = False
            self.formule_cumac_python = False
            self.formule_description = False
            return {'warning': {
                'title': 'PDF remplacé — analyse obsolète',
                'message': (
                    "Le PDF a été modifié. L'analyse IA précédente a été réinitialisée.\n"
                    "Cliquez sur « Réanalyser avec l'IA » pour recalculer la formule."
                ),
            }}

    def action_reanalyser_fiche(self):
        """Lance l'analyse Claude du PDF et met à jour la formule + le guide."""
        self.ensure_one()
        from .wizard_cee import _appel_claude_analyse_complete

        if not self.fiche_pdf:
            raise UserError("Aucun PDF n'est attaché à cette opération.")

        api_key = self.env['ir.config_parameter'].sudo().get_param(
            'ibatix.anthropic_api_key', ''
        )
        if not api_key:
            raise UserError(
                "Clé API Anthropic non configurée.\n"
                "Ajoutez 'ibatix.anthropic_api_key' dans "
                "Paramètres → Technique → Paramètres système."
            )

        pdf_bytes = base64.b64decode(self.fiche_pdf)
        result = _appel_claude_analyse_complete(
            pdf_bytes, api_key, self.code or '', self.name or ''
        )

        formule = result.get('formule_cumac_python', '')
        if 'def ' in formule:
            raise UserError(
                "L'analyse IA a retourné une formule invalide (définition de fonction).\n"
                "Réessayez ou vérifiez le PDF."
            )

        guide = result.get('guide_html') or '<p><em>Aucun résultat retourné.</em></p>'
        self.write({
            'guide_html': guide,
            'champs_requis': result.get('champs_requis', ''),
            'formule_cumac_python': formule,
            'formule_description': result.get('formule_description', ''),
            'formule_analysee': True,
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Analyse terminée',
                'message': (
                    f"{self.code} mis à jour. "
                    f"Champs requis : {result.get('champs_requis', '—')}"
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_reinitialiser_analyse(self):
        """Efface l'analyse IA pour forcer une nouvelle analyse."""
        self.ensure_one()
        self.write({
            'formule_analysee': False,
            'guide_html': False,
            'champs_requis': False,
            'formule_cumac_python': False,
            'formule_description': False,
        })
