from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    operation_cee_id = fields.Many2one(
        'ibatix.operation.cee',
        related='product_id.product_tmpl_id.operation_cee_id',
        string='Opération CEE',
        store=True,
    )
    prime_cee = fields.Float(
        string='Prime CEE (€)',
        digits=(10, 2),
        default=0.0,
        help="Prime CEE calculée pour cette ligne (Cumac × Valorisation).",
    )
    cumac_cee = fields.Float(
        string='Cumac (MWhc)',
        digits=(10, 3),
        help="Volume de Cumac retenu pour le calcul de la prime.",
    )
    valo_cee = fields.Float(
        string='Valorisation (€/MWhc)',
        digits=(10, 4),
        help="Prix unitaire du MWhc retenu (issu du contrat délégataire).",
    )
    params_techniques_cee = fields.Text(
        string='Paramètres techniques CEE',
        help="Informations techniques renseignées lors du calcul de la prime.",
    )

    def action_ouvrir_wizard_cee(self):
        """Ouvre le wizard de calcul de prime CEE pour cette ligne."""
        self.ensure_one()

        # Pré-remplissage : Cumac depuis le délégataire.operation
        cumac = 0.0
        valo = 0.0
        delegataire = self.order_id.delegataire_cee_id
        contrat = self.order_id.contrat_cee_id
        categorie = self.order_id.partner_id.categorie_precarite

        if delegataire and self.operation_cee_id:
            op = delegataire.operation_ids.filtered(
                lambda o: o.code == self.operation_cee_id.code
            )[:1]
            if op:
                if categorie == 'precaire':
                    cumac = op.cumac_precaire or op.cumac_total
                elif categorie == 'modeste':
                    cumac = op.cumac_precaire or op.cumac_total
                else:
                    cumac = op.cumac_classique or op.cumac_total

        if contrat:
            if categorie in ('precaire', 'modeste'):
                valo = contrat.valo_precaire_client
            else:
                valo = contrat.valo_classique_client

        # Pré-calculer le cumac si la formule est déjà connue sur l'opération
        formule = self.operation_cee_id.formule_cumac_python if self.operation_cee_id else ''
        cumac_auto = 0.0
        if formule and not self.cumac_cee and not cumac:
            from .wizard_cee import _evaluer_cumac
            cumac_auto = _evaluer_cumac(formule, self.product_uom_qty, 0, 0, 0, 0, 0, 0)

        wizard = self.env['ibatix.wizard.cee'].create({
            'sale_line_id': self.id,
            'cumac_cee': self.cumac_cee or cumac or cumac_auto,
            'valo_cee': self.valo_cee or valo,
            'surface_m2': self.product_uom_qty,  # surface = quantité de la ligne
        })

        return {
            'type': 'ir.actions.act_window',
            'name': f"Prime CEE — {self.operation_cee_id.display_name or ''}",
            'res_model': 'ibatix.wizard.cee',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
