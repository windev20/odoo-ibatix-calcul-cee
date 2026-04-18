from odoo import fields, models


class IbatixOperationCee(models.Model):
    _inherit = 'ibatix.operation.cee'

    # ── Résultats de l'analyse IA (stockés une fois pour toute) ─────────────
    champs_requis = fields.Char(
        string='Champs techniques requis',
        help="Noms des variables séparés par virgule : surface_m2,resistance_thermique,...",
    )
    formule_cumac_python = fields.Text(
        string='Formule Cumac (Python)',
        help="Expression Python évaluable. Variables : surface_m2, resistance_thermique, "
             "puissance_kw, cop, scop, etas, nb_logements.",
    )
    formule_description = fields.Char(
        string='Description de la formule',
    )
    formule_analysee = fields.Boolean(
        string='Formule analysée par l\'IA',
        default=False,
    )
