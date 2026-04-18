from odoo import fields, models


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
