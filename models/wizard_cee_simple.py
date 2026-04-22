from odoo import fields, models
from odoo.exceptions import UserError


class WizardCeeSimple(models.TransientModel):
    _name = 'ibatix.wizard.cee.simple'
    _description = "Paramètres simplifiés pour l'opération CEE"

    line_id = fields.Many2one('sale.order.line', required=True, ondelete='cascade')
    operation_name = fields.Char(related='line_id.operation_cee_id.display_name', string='Opération')

    surface_chauffee = fields.Float(string='Surface chauffée par le système (m²)', digits=(10, 2))
    type_logement = fields.Selection([
        ('maison', 'Maison individuelle'),
        ('appartement', 'Appartement'),
    ], string='Type de logement')
    type_energie = fields.Selection([
        ('electricite', 'Électricité'),
        ('gaz', 'Gaz naturel'),
        ('fioul', 'Fioul'),
        ('bois', 'Bois / Biomasse'),
        ('autre', 'Autre'),
    ], string='Énergie de chauffage avant travaux')

    def action_confirmer(self):
        self.ensure_one()
        if not self.surface_chauffee:
            raise UserError("Veuillez renseigner la surface chauffée.")
        if not self.type_logement:
            raise UserError("Veuillez renseigner le type de logement.")
        if not self.type_energie:
            raise UserError("Veuillez renseigner l'énergie de chauffage avant travaux.")

        line = self.line_id
        line.write({
            'surface_chauffee_cee': self.surface_chauffee,
            'type_logement_cee': self.type_logement,
            'type_energie_cee': self.type_energie,
        })

        # Auto-calcul cumac + prime si formule disponible
        op = line.operation_cee_id
        if op and op.formule_cumac_python:
            from .wizard_cee import _evaluer_cumac
            cumac = _evaluer_cumac(
                op.formule_cumac_python,
                surface_chauffee=self.surface_chauffee,
                surface_m2=self.surface_chauffee,
                type_logement=self.type_logement,
                zone_climatique=line.zone_climatique_cee or '',
            )
            valo = line.valo_cee or 0.0
            prime = cumac * valo / 1000 if valo else 0.0
            line.write({'cumac_cee': cumac, 'prime_cee': prime})

        line._calculer_prime_mpr()
        return {'type': 'ir.actions.act_window_close'}
