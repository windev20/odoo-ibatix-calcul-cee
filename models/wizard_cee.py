import base64
import json
import logging
import time
import urllib.error
import urllib.request

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

_CHAMPS_DISPONIBLES = (
    "surface_m2 (surface en m²), "
    "surface_chauffee (surface chauffée par le système en m²), "
    "resistance_thermique (résistance thermique R en m².K/W), "
    "puissance_kw (puissance nominale en kW), "
    "cop (COP), "
    "scop (SCOP), "
    "etas (efficacité saisonnière ηs en %), "
    "nb_logements (nombre de logements), "
    "zone_climatique (zone climatique string : 'h1', 'h2' ou 'h3'), "
    "facteur_zone (valeur numérique : H1=1.3 H2=1.0 H3=0.8), "
    "type_logement (string : 'maison' ou 'appartement'), "
    "facteur_logement (valeur numérique : maison=1.0 appartement=0.75), "
    "profil_soutirage (profil de soutirage chauffe-eau : string 'M', 'L' ou 'XL'), "
    "efficacite_energetique (efficacité énergétique en % : float, ex. 95.0, 100.0, 110.0), "
    "classe_regulation_iso52120 (classe de régulation BAR-TH-173 : string 'a' ou 'b'), "
    "uw (coefficient de transmission thermique Uw en W/m2.K : float), "
    "sw (facteur solaire Sw : float), "
    "nb_fenetres (nombre de fenetres ou portes-fenetres posees : entier), "
    "type_fenetre (type de fenetre : string 'toiture', 'double' ou 'autre'), "
    "rendement_saisonnier (rendement saisonnier en % : float, ex. 87.3), "
    "label_energie (classe energetique : string, ex. 'A+', 'A++'), "
    "type_vmc (type de ventilation dans les locaux : string 'naturelle', 'simple_flux', 'double_flux', 'parietodynamique' ou 'vec'), "
    "surface_capteurs (surface des capteurs solaires en m2 : float), "
    "nb_equipements (nombre d'equipements installes : entier), "
    "epaisseur_isolant (epaisseur de l'isolant en mm : float), "
    "volume_ballon (volume du ballon d'eau chaude en litres : float), "
    "secteur_activite (secteur d'activite du batiment : string parmi 'bureaux', 'enseignement', "
    "'commerces', 'hotellerie', 'sante', 'logistique', 'industrie', 'agriculture', 'autre'), "
    "ug (coefficient de transmission thermique du vitrage seul Ug en W/m2.K : float), "
    "type_serre (type de serre agricole : string 'maraichere' ou 'horticole'), "
    "thermicite (niveau de thermicite de la serre : string 'froide', 'temperee' ou 'chaude'), "
    "delta_t (ecart de temperature du process industriel en degres C : float), "
    "type_condensation (type de condensation : string 'eau' ou 'air'), "
    "mode_fonctionnement (mode de fonctionnement de l'equipement : string libre)"
)


def _evaluer_cumac(formule, surface_m2=0.0, resistance_thermique=0.0,
                   puissance_kw=0.0, cop=0.0, scop=0.0, etas=0.0,
                   nb_logements=0, surface_chauffee=0.0,
                   type_logement='', zone_climatique='',
                   profil_soutirage='', efficacite_energetique=0.0,
                   classe_regulation_iso52120='',
                   secteur_activite='', delta_t=0.0, type_condensation='',
                   mode_fonctionnement='', type_serre='', thermicite='',
                   surface_capteurs=0.0, nb_equipements=0,
                   epaisseur_isolant=0.0, volume_ballon=0.0,
                   rendement_saisonnier=0.0, ug=0.0):
    """Évalue la formule Python de cumac dans un contexte sécurisé."""
    if not formule:
        return 0.0
    ctx = {
        'surface_m2': surface_m2 or 0.0,
        'surface_chauffee': surface_chauffee or 0.0,
        'resistance_thermique': resistance_thermique or 0.0,
        'puissance_kw': puissance_kw or 0.0,
        'cop': cop or 0.0,
        'scop': scop or 0.0,
        'etas': etas or 0.0,
        'nb_logements': nb_logements or 0,
        'zone_climatique': zone_climatique or '',
        'facteur_zone': {'h1': 1.3, 'h2': 1.0, 'h3': 0.8}.get(zone_climatique or '', 1.0),
        'type_logement': type_logement or '',
        'facteur_logement': {'maison': 1.0, 'appartement': 0.75}.get(type_logement or '', 1.0),
        'profil_soutirage': profil_soutirage or '',
        'efficacite_energetique': efficacite_energetique or 0.0,
        'classe_regulation_iso52120': classe_regulation_iso52120 or '',
        'secteur_activite': secteur_activite or '',
        'delta_t': delta_t or 0.0,
        'type_condensation': type_condensation or '',
        'mode_fonctionnement': mode_fonctionnement or '',
        'type_serre': type_serre or '',
        'thermicite': thermicite or '',
        'surface_capteurs': surface_capteurs or 0.0,
        'nb_equipements': nb_equipements or 0,
        'epaisseur_isolant': epaisseur_isolant or 0.0,
        'volume_ballon': volume_ballon or 0.0,
        'rendement_saisonnier': rendement_saisonnier or 0.0,
        'ug': ug or 0.0,
        'max': max, 'min': min, 'round': round,
    }
    try:
        return float(eval(formule, {"__builtins__": {}}, ctx))  # noqa: S307
    except Exception as e:
        _logger.warning("Erreur évaluation formule cumac '%s': %s", formule, e)
        return 0.0


def _appel_claude_analyse_complete(pdf_bytes, api_key, operation_code, operation_name):
    """
    Analyse la fiche PDF CEE via Claude → guide HTML + champs requis + formule Cumac.
    Retourne dict : guide_html, champs_requis, formule_cumac_python, formule_description.
    """
    pdf_b64 = base64.b64encode(pdf_bytes).decode('utf-8')

    prompt = (
        f"Tu es un expert CEE français. Opération : {operation_code} — {operation_name}.\n\n"
        f"Variables disponibles dans notre logiciel : {_CHAMPS_DISPONIBLES}\n\n"
        "Analyse cette fiche CEE et retourne UN SEUL objet JSON valide (sans markdown ni balises), "
        "avec exactement ces 5 clés :\n"
        "{\n"
        '  "guide_html": "<h4>...</h4>...",\n'
        '  "champs_requis": "var1,var2",\n'
        '  "champs_eligibilite": "var3,var4",\n'
        '  "formule_cumac_python": "expression Python",\n'
        '  "formule_description": "description lisible"\n'
        "}\n\n"
        "Règles :\n"
        "- guide_html : HTML compact (<h4>,<ul>,<li>,<strong>) listant conditions d'éligibilité, "
        "données techniques à collecter, documents justificatifs. En français. Sans CSS.\n"
        "- champs_requis : UNIQUEMENT les noms de variables ci-dessus nécessaires au CALCUL du cumac, "
        "séparés par virgule. Inclure zone_climatique si la formule varie selon la zone. "
        "INTERDIT dans champs_requis : facteur_zone, facteur_logement (ils sont calcules automatiquement "
        "depuis zone_climatique et type_logement — ne jamais les lister).\n"
        "- champs_eligibilite : noms de variables ci-dessus necessaires pour VERIFIER l'eligibilite "
        "et figurer sur les documents (facture, attestation). Separes par virgule. "
        "REGLES ABSOLUES pour champs_eligibilite :\n"
        "  1. Ne JAMAIS repeter une variable deja presente dans champs_requis.\n"
        "  2. Ne JAMAIS inclure facteur_zone ni facteur_logement (valeurs calculees, pas saisies).\n"
        "  3. N'inclure QUE des variables ayant une valeur saisie par l'utilisateur sur l'attestation "
        "(ex: uw, sw, nb_fenetres, type_fenetre, epaisseur_isolant, volume_ballon, rendement_saisonnier, "
        "label_energie, type_vmc, surface_capteurs, nb_equipements, secteur_activite, ug).\n"
        "  4. Si aucune variable supplementaire n'est requise pour l'attestation, laisser champs_eligibilite vide (\"\").\n"
        "Exemple pour BAR-EN-104 : uw,sw,nb_fenetres,type_fenetre\n"
        "- formule_cumac_python : UNE SEULE expression Python evaluable directement. "
        "INTERDIT : def, lambda, return, blocs if multiligne. "
        "Integre les constantes directement. "
        "Utilise facteur_zone et facteur_logement pour les facteurs numeriques. "
        "Exemple : surface_m2 * resistance_thermique * 36.5 * facteur_zone\n"
        "- formule_description : formule lisible pour l'utilisateur.\n"
        "- NOMMAGE OBLIGATOIRE : sw (jamais facteur_solaire), "
        "secteur_activite (jamais secteur_d_activite ni secteur_industrie), "
        "ug pour le vitrage seul, type_serre pour les serres agricoles, "
        "thermicite pour le niveau thermique des serres.\n"
        "Reponds uniquement en JSON."
    )

    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2048,
        "messages": [{
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
        }],
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

    empty = {'guide_html': '', 'champs_requis': '', 'champs_eligibilite': '', 'formule_cumac_python': '', 'formule_description': ''}

    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read().decode('utf-8'))
            raw = body.get('content', [{}])[0].get('text', '').strip()

            if raw.startswith('```'):
                lines = raw.splitlines()
                raw = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])

            result = json.loads(raw)
            return {
                'guide_html': result.get('guide_html', ''),
                'champs_requis': result.get('champs_requis', ''),
                'champs_eligibilite': result.get('champs_eligibilite', ''),
                'formule_cumac_python': result.get('formule_cumac_python', ''),
                'formule_description': result.get('formule_description', ''),
            }
        except json.JSONDecodeError as e:
            raw_preview = locals().get('raw', '')[:500]
            _logger.error("Claude : réponse JSON invalide — %s\nRaw: %s", e, raw_preview)
            return empty
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 65 * (attempt + 1)
                _logger.warning("Claude API 429 — attente %ds (tentative %d/4)", wait, attempt + 1)
                time.sleep(wait)
                continue
            _logger.error("Claude API erreur %s : %s", e.code, e.read().decode())
            return empty
        except Exception as e:
            _logger.error("Claude API exception : %s", e)
            return empty

    _logger.error("Claude API : échec après 4 tentatives (429 persistant)")
    return empty


class WizardCee(models.TransientModel):
    _name = 'ibatix.wizard.cee'
    _description = "Calcul de la prime CEE"

    # ── Contexte (lecture seule) ─────────────────────────────────────────────
    sale_line_id = fields.Many2one('sale.order.line', required=True, readonly=True)
    product_line_id = fields.Many2one('sale.order.line', readonly=True)
    champs_manquants_produit = fields.Char(readonly=True)
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
    champs_eligibilite = fields.Char(
        related='operation_cee_id.champs_eligibilite',
        string="Champs d'eligibilite",
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

    # ── Guide technique ──────────────────────────────────────────────────────
    guide_technique = fields.Html(string='Guide technique', readonly=True, sanitize=False)
    fiche_analysee = fields.Boolean(default=False)

    # ── Paramètres techniques ────────────────────────────────────────────────
    marque = fields.Char(string='Marque')
    modele = fields.Char(string='Modèle / Référence')
    surface_m2 = fields.Float(string='Surface (m²)', digits=(10, 2))
    surface_chauffee = fields.Float(string='Surface chauffée (m²)', digits=(10, 2))
    resistance_thermique = fields.Float(string='Résistance thermique R (m².K/W)', digits=(10, 2))
    puissance_kw = fields.Float(string='Puissance (kW)', digits=(10, 2))
    cop = fields.Float(string='COP', digits=(10, 2))
    scop = fields.Float(string='SCOP', digits=(10, 2))
    etas = fields.Float(string='ηs (%)', digits=(10, 1))
    nb_logements = fields.Integer(string='Nombre de logements')
    type_energie = fields.Selection([
        ('electricite', 'Électricité'),
        ('gaz', 'Gaz naturel'),
        ('fioul', 'Fioul'),
        ('bois', 'Bois / Biomasse'),
        ('autre', 'Autre'),
    ], string="Énergie de chauffage avant travaux")
    type_logement = fields.Selection([
        ('maison', 'Maison individuelle'),
        ('appartement', 'Appartement'),
    ], string='Type de logement')
    zone_climatique = fields.Selection([
        ('h1', 'Zone H1 (Nord / Est)'),
        ('h2', 'Zone H2 (Centre / Ouest)'),
        ('h3', 'Zone H3 (Méditerranée)'),
    ], string='Zone climatique')
    profil_soutirage = fields.Selection([
        ('M', 'M'),
        ('L', 'L'),
        ('XL', 'XL'),
    ], string='Profil de soutirage')
    efficacite_energetique = fields.Float(string='Efficacité énergétique (%)', digits=(10, 1))
    type_application_pac = fields.Selection([
        ('basse_temperature', 'Basse température (35°C — plancher/plafond/ventiloconvecteur)'),
        ('haute_temperature', 'Moyenne/haute température (55°C — radiateurs)'),
    ], string='Application PAC')
    usage_pac = fields.Selection([
        ('chauffage', 'Chauffage seul'),
        ('chauffage_ecs', 'Chauffage + eau chaude sanitaire'),
    ], string='Usage PAC')
    classe_regulateur = fields.Selection([
        ('IV', 'Classe IV'), ('V', 'Classe V'), ('VI', 'Classe VI'),
        ('VII', 'Classe VII'), ('VIII', 'Classe VIII'),
    ], string='Classe du régulateur')
    classe_regulation_iso52120 = fields.Selection([
        ('a', 'Classe A (NF EN ISO 52120-1)'),
        ('b', 'Classe B (NF EN ISO 52120-1)'),
    ], string='Classe de régulation (ISO 52120-1)')
    notes_techniques = fields.Text(string='Notes complémentaires')

    # ── Champs d'éligibilité ─────────────────────────────────────────────────
    uw = fields.Float(string='Uw (W/m².K)', digits=(10, 3))
    sw = fields.Float(string='Sw — Facteur solaire', digits=(10, 3))
    nb_fenetres = fields.Integer(string='Nombre de fenêtres')
    type_fenetre = fields.Selection([
        ('toiture', 'Fenêtre de toiture'),
        ('double', 'Double fenêtre'),
        ('autre', 'Fenêtre / porte-fenêtre'),
    ], string='Type de fenêtre')
    rendement_saisonnier = fields.Float(string='Rendement saisonnier (%)', digits=(10, 1))
    label_energie = fields.Char(string='Classe énergétique')
    type_vmc = fields.Selection([
        ('naturelle', 'Ventilation naturelle'),
        ('simple_flux', 'VMC simple flux'),
        ('double_flux', 'VMC double flux'),
        ('parietodynamique', 'Vitrage pariétodynamique'),
        ('vec', 'VEC — Ventilation par extraction centralisée'),
    ], string='Système de ventilation')
    surface_capteurs = fields.Float(string='Surface capteurs (m²)', digits=(10, 2))
    nb_equipements = fields.Integer(string='Nombre d\'equipements')
    epaisseur_isolant = fields.Float(string='Épaisseur isolant (mm)', digits=(10, 0))
    volume_ballon = fields.Float(string='Volume ballon (L)', digits=(10, 0))
    secteur_activite = fields.Selection([
        ('bureaux', 'Bureaux'),
        ('enseignement', 'Enseignement'),
        ('commerces', 'Commerces / Grande distribution'),
        ('hotellerie', 'Hôtellerie / Restauration'),
        ('sante', 'Santé / Médico-social'),
        ('logistique', 'Logistique / Entrepôts'),
        ('industrie', 'Industrie'),
        ('agriculture', 'Agriculture'),
        ('autre', 'Autre'),
    ], string="Secteur d'activité")
    ug = fields.Float(string='Ug — Vitrage seul (W/m².K)', digits=(10, 3))
    type_serre = fields.Selection([
        ('maraichere', 'Maraîchère'),
        ('horticole', 'Horticole'),
    ], string='Type de serre')
    thermicite = fields.Selection([
        ('froide', 'Froide (< 12°C)'),
        ('temperee', 'Tempérée (12-17°C)'),
        ('chaude', 'Chaude (> 17°C)'),
    ], string='Thermicité de la serre')
    delta_t = fields.Float(string='Delta T process (°C)', digits=(10, 1))
    type_condensation = fields.Selection([
        ('eau', 'À eau'),
        ('air', 'À air'),
    ], string='Type de condensation')
    mode_fonctionnement = fields.Char(string='Mode de fonctionnement')

    # ── Sous-traitance ───────────────────────────────────────────────────────
    sous_traitant_id = fields.Many2one('ibatix.installateur', string='Sous-traitant')
    sous_traitant_street = fields.Char(related='sous_traitant_id.street', string='Adresse', readonly=True)
    sous_traitant_zip = fields.Char(related='sous_traitant_id.zip', string='Code postal', readonly=True)
    sous_traitant_city = fields.Char(related='sous_traitant_id.city', string='Ville', readonly=True)
    sous_traitant_phone = fields.Char(related='sous_traitant_id.phone', string='Téléphone', readonly=True)
    sous_traitant_email = fields.Char(related='sous_traitant_id.email', string='Email', readonly=True)
    sous_traitant_qualification_ids = fields.One2many(
        related='sous_traitant_id.qualification_ids',
        string='Qualifications RGE',
        readonly=True,
    )

    # ── Calcul ───────────────────────────────────────────────────────────────
    cumac_cee = fields.Float(string='Cumac retenu (MWhc)', digits=(10, 3))
    valo_cee = fields.Float(string='Valorisation (€/MWhc)', digits=(10, 4))
    prime_cee = fields.Float(
        string='Prime CEE calculée (€)',
        compute='_compute_prime_cee',
        digits=(10, 2),
    )

    @api.depends('cumac_cee', 'valo_cee')
    def _compute_prime_cee(self):
        for rec in self:
            rec.prime_cee = rec.cumac_cee * rec.valo_cee / 1000

    prime_mpr_preview = fields.Float(
        string='Estimation MPR (EUR)',
        compute='_compute_prime_mpr_preview',
        digits=(10, 2),
    )
    prime_mpr_ecrete_preview = fields.Boolean(
        string='Ecretement MPR',
        compute='_compute_prime_mpr_preview',
    )
    prime_mpr_eligible = fields.Boolean(
        string='Eligibilite MPR',
        compute='_compute_prime_mpr_preview',
    )
    prime_mpr_explication = fields.Char(
        string='Explication MPR',
        compute='_compute_prime_mpr_preview',
    )

    @api.depends(
        'prime_cee', 'surface_m2', 'surface_chauffee',
        'sale_line_id', 'sale_line_id.operation_cee_id',
        'sale_line_id.order_id.partner_id.categorie_precarite',
    )
    def _compute_prime_mpr_preview(self):
        _labels = {
            'precaire': 'Tres modeste (bleu, taux 90 %)',
            'modeste': 'Modeste (jaune, taux 75 %)',
            'intermediaire': 'Intermediaire (violet, taux 60 %)',
        }
        for rec in self:
            op = rec.sale_line_id.operation_cee_id
            if not op or not op.eligible_mpr:
                rec.prime_mpr_preview = 0.0
                rec.prime_mpr_ecrete_preview = False
                rec.prime_mpr_eligible = False
                rec.prime_mpr_explication = "Cette operation n'est pas eligible a MaPrimeRenov'."
                continue
            categorie = rec.categorie_precarite
            if categorie == 'precaire':
                taux, forfait_unitaire = 0.90, op.prime_mpr_bleu
            elif categorie == 'modeste':
                taux, forfait_unitaire = 0.75, op.prime_mpr_jaune
            elif categorie == 'intermediaire':
                taux, forfait_unitaire = 0.60, op.prime_mpr_violet
            else:
                rec.prime_mpr_preview = 0.0
                rec.prime_mpr_ecrete_preview = False
                rec.prime_mpr_eligible = False
                rec.prime_mpr_explication = "Menage superieur : non eligible a MaPrimeRenov' par geste."
                continue
            rec.prime_mpr_eligible = True
            label_cat = _labels.get(categorie, categorie)
            if not forfait_unitaire:
                rec.prime_mpr_preview = 0.0
                rec.prime_mpr_ecrete_preview = False
                rec.prime_mpr_explication = f"Bareme non renseigne pour la categorie {label_cat}."
                continue
            if op.type_calcul_mpr == 'par_m2':
                surface = rec.surface_m2 or rec.surface_chauffee or 0.0
                forfait = forfait_unitaire * surface
            else:
                forfait = forfait_unitaire
            ecrete = False
            plafond = op.plafond_depense_mpr
            if plafond:
                next_line = rec.sale_line_id._get_next_product_line()
                depense = next_line.price_total if next_line else 0.0
                depense_eligible = min(depense, plafond)
                plafond_ecr = max(0.0, taux * depense_eligible - (rec.prime_cee or 0.0))
                if forfait > plafond_ecr:
                    forfait = plafond_ecr
                    ecrete = True
            rec.prime_mpr_preview = round(forfait, 2)
            rec.prime_mpr_ecrete_preview = ecrete
            rec.prime_mpr_eligible = True
            taux_pct = int(taux * 100)
            if ecrete:
                rec.prime_mpr_explication = (
                    f"Categorie {label_cat}. "
                    f"Ecretement : {taux_pct} % x {depense_eligible:.0f} EUR (depense eligible)"
                    f" - {rec.prime_cee:.0f} EUR (prime CEE) = {forfait:.0f} EUR."
                )
            else:
                plafond_txt = f", plafond depense {plafond:.0f} EUR" if plafond else ""
                rec.prime_mpr_explication = (
                    f"Categorie {label_cat}. "
                    f"Forfait {forfait:.0f} EUR (taux {taux_pct} %{plafond_txt})."
                )

    @api.onchange('sous_traitant_id')
    def _onchange_sous_traitant_id(self):
        if not self.sous_traitant_id:
            return
        from datetime import date
        today = date.today()
        qualifs_valides = self.sous_traitant_id.qualification_ids.filtered(
            lambda q: not q.end_date or q.end_date >= today
        )
        if not qualifs_valides:
            return {'warning': {
                'title': '⚠️ Attention — Sous-traitant sans RGE valide',
                'message': (
                    f"{self.sous_traitant_id.name} n'a aucune qualification RGE en cours de validité "
                    f"à la date d'aujourd'hui.\n\n"
                    "Les travaux sous-traités à cette entreprise ne pourront pas être valorisés "
                    "dans le cadre du dispositif CEE."
                ),
            }}

    @api.onchange('surface_m2', 'surface_chauffee', 'resistance_thermique',
                  'puissance_kw', 'cop', 'scop', 'etas', 'nb_logements',
                  'zone_climatique', 'type_logement', 'profil_soutirage',
                  'efficacite_energetique', 'classe_regulation_iso52120',
                  'secteur_activite', 'delta_t', 'type_condensation',
                  'mode_fonctionnement', 'type_serre', 'thermicite',
                  'surface_capteurs', 'nb_equipements',
                  'epaisseur_isolant', 'volume_ballon', 'rendement_saisonnier', 'ug')
    def _onchange_params_techniques(self):
        formule = self.operation_cee_id.formule_cumac_python if self.operation_cee_id else ''
        if not formule:
            return
        self.cumac_cee = _evaluer_cumac(
            formule,
            surface_m2=self.surface_m2,
            resistance_thermique=self.resistance_thermique,
            puissance_kw=self.puissance_kw,
            cop=self.cop,
            scop=self.scop,
            etas=self.etas,
            nb_logements=self.nb_logements,
            surface_chauffee=self.surface_chauffee,
            type_logement=self.type_logement or '',
            zone_climatique=self.zone_climatique or '',
            profil_soutirage=self.profil_soutirage or '',
            efficacite_energetique=self.efficacite_energetique,
            classe_regulation_iso52120=self.classe_regulation_iso52120 or '',
            secteur_activite=self.secteur_activite or '',
            delta_t=self.delta_t,
            type_condensation=self.type_condensation or '',
            mode_fonctionnement=self.mode_fonctionnement or '',
            type_serre=self.type_serre or '',
            thermicite=self.thermicite or '',
            surface_capteurs=self.surface_capteurs,
            nb_equipements=self.nb_equipements,
            epaisseur_isolant=self.epaisseur_isolant,
            volume_ballon=self.volume_ballon,
            rendement_saisonnier=self.rendement_saisonnier,
            ug=self.ug,
        )

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_analyser_fiche(self):
        """Appelle Claude pour analyser la fiche PDF : guide + formule + champs requis."""
        self.ensure_one()
        op = self.operation_cee_id
        if not op or not op.fiche_pdf:
            self.guide_technique = (
                "<p><em>Aucune fiche PDF renseignée sur cette opération CEE. "
                "Ajoutez-la dans Configuration › Opérations CEE.</em></p>"
            )
            self.fiche_analysee = True
            return self._reopen()

        api_key = self.env['ir.config_parameter'].sudo().get_param(
            'ibatix.anthropic_api_key', ''
        )
        if not api_key:
            self.guide_technique = (
                "<p><strong>Clé API Anthropic non configurée.</strong> "
                "Ajoutez <code>ibatix.anthropic_api_key</code> dans "
                "Paramètres › Technique › Paramètres système.</p>"
            )
            self.fiche_analysee = True
            return self._reopen()

        pdf_bytes = base64.b64decode(op.fiche_pdf)
        result = _appel_claude_analyse_complete(
            pdf_bytes, api_key, op.code or '', op.name or ''
        )

        guide = result['guide_html'] or (
            "<p><em>L'analyse n'a pas retourné de résultat. "
            "Vérifiez les logs serveur.</em></p>"
        )
        self.guide_technique = guide
        self.fiche_analysee = True

        # Sauvegarde persistante sur l'opération
        op.sudo().write({
            'guide_html': guide,
            'champs_requis': result['champs_requis'],
            'champs_eligibilite': result['champs_eligibilite'],
            'formule_cumac_python': result['formule_cumac_python'],
            'formule_description': result['formule_description'],
            'formule_analysee': True,
        })

        if result['formule_cumac_python']:
            self.cumac_cee = _evaluer_cumac(
                result['formule_cumac_python'],
                surface_m2=self.surface_m2,
                resistance_thermique=self.resistance_thermique,
                puissance_kw=self.puissance_kw,
                cop=self.cop,
                scop=self.scop,
                etas=self.etas,
                nb_logements=self.nb_logements,
                surface_chauffee=self.surface_chauffee,
                type_logement=self.type_logement or '',
                zone_climatique=self.zone_climatique or '',
                profil_soutirage=self.profil_soutirage or '',
                efficacite_energetique=self.efficacite_energetique,
                classe_regulation_iso52120=self.classe_regulation_iso52120 or '',
                secteur_activite=self.secteur_activite or '',
                delta_t=self.delta_t,
                type_condensation=self.type_condensation or '',
                mode_fonctionnement=self.mode_fonctionnement or '',
                type_serre=self.type_serre or '',
                thermicite=self.thermicite or '',
                surface_capteurs=self.surface_capteurs,
                nb_equipements=self.nb_equipements,
                epaisseur_isolant=self.epaisseur_isolant,
                volume_ballon=self.volume_ballon,
                rendement_saisonnier=self.rendement_saisonnier,
                ug=self.ug,
            )

        return self._reopen()

    def action_confirmer(self):
        """Enregistre la prime et tous les paramètres techniques sur la ligne de devis."""
        self.ensure_one()
        self.sale_line_id.write({
            'prime_cee': self.prime_cee,
            'cumac_cee': self.cumac_cee,
            'valo_cee': self.valo_cee,
            'params_techniques_cee': self._build_params_text(),
            # Persistance des paramètres techniques
            'marque_cee': self.marque,
            'modele_cee': self.modele,
            'surface_m2_cee': self.surface_m2,
            'surface_chauffee_cee': self.surface_chauffee,
            'resistance_thermique_cee': self.resistance_thermique,
            'puissance_kw_cee': self.puissance_kw,
            'cop_cee': self.cop,
            'scop_cee': self.scop,
            'etas_cee': self.etas,
            'nb_logements_cee': self.nb_logements,
            'type_energie_cee': self.type_energie or False,
            'type_logement_cee': self.type_logement or False,
            'zone_climatique_cee': self.zone_climatique or False,
            'profil_soutirage_cee': self.profil_soutirage or False,
            'efficacite_energetique_cee': self.efficacite_energetique,
            'type_application_pac_cee': self.type_application_pac or False,
            'usage_pac_cee': self.usage_pac or False,
            'classe_regulateur_cee': self.classe_regulateur or False,
            'classe_regulation_iso52120_cee': self.classe_regulation_iso52120 or False,
            'notes_techniques_cee': self.notes_techniques,
            # Champs d'éligibilité
            'uw_cee': self.uw,
            'sw_cee': self.sw,
            'nb_fenetres_cee': self.nb_fenetres,
            'type_fenetre_cee': self.type_fenetre or False,
            'rendement_saisonnier_cee': self.rendement_saisonnier,
            'label_energie_cee': self.label_energie,
            'type_vmc_cee': self.type_vmc or False,
            'surface_capteurs_cee': self.surface_capteurs,
            'nb_equipements_cee': self.nb_equipements,
            'epaisseur_isolant_cee': self.epaisseur_isolant,
            'volume_ballon_cee': self.volume_ballon,
            'secteur_activite_cee': self.secteur_activite or False,
            'ug_cee': self.ug,
            'type_serre_cee': self.type_serre or False,
            'thermicite_cee': self.thermicite or False,
            'delta_t_cee': self.delta_t,
            'type_condensation_cee': self.type_condensation or False,
            'mode_fonctionnement_cee': self.mode_fonctionnement,
            'sous_traitant_cee_id': self.sous_traitant_id.id or False,
        })
        self.sale_line_id._calculer_prime_mpr()
        return {'type': 'ir.actions.act_window_close'}

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': f"Prime CEE — {self.operation_cee_id.display_name or ''}",
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _build_params_text(self):
        lines = []
        if self.marque:
            lines.append(f"Marque : {self.marque}")
        if self.modele:
            lines.append(f"Modèle : {self.modele}")
        if self.surface_m2:
            lines.append(f"Surface : {self.surface_m2} m²")
        if self.surface_chauffee:
            lines.append(f"Surface chauffée : {self.surface_chauffee} m²")
        if self.resistance_thermique:
            lines.append(f"R : {self.resistance_thermique} m².K/W")
        if self.puissance_kw:
            lines.append(f"Puissance : {self.puissance_kw} kW")
        if self.cop:
            lines.append(f"COP : {self.cop}")
        if self.scop:
            lines.append(f"SCOP : {self.scop}")
        if self.etas:
            lines.append(f"ηs : {self.etas} %")
        if self.nb_logements:
            lines.append(f"Nb logements : {self.nb_logements}")
        if self.type_logement:
            labels = dict(self._fields['type_logement'].selection)
            lines.append(f"Type logement : {labels.get(self.type_logement, self.type_logement)}")
        if self.zone_climatique:
            labels = dict(self._fields['zone_climatique'].selection)
            lines.append(f"Zone climatique : {labels.get(self.zone_climatique, self.zone_climatique)}")
        if self.type_energie:
            labels = dict(self._fields['type_energie'].selection)
            lines.append(f"Énergie remplacée : {labels.get(self.type_energie, self.type_energie)}")
        if self.notes_techniques:
            lines.append(f"Notes : {self.notes_techniques}")
        if self.uw:
            lines.append(f"Uw : {self.uw} W/m2.K")
        if self.sw:
            lines.append(f"Sw : {self.sw}")
        if self.nb_fenetres:
            lines.append(f"Nb fenetres : {self.nb_fenetres}")
        if self.type_fenetre:
            labels = dict(self._fields['type_fenetre'].selection)
            lines.append(f"Type fenetre : {labels.get(self.type_fenetre, self.type_fenetre)}")
        if self.rendement_saisonnier:
            lines.append(f"Rendement saisonnier : {self.rendement_saisonnier} %")
        if self.label_energie:
            lines.append(f"Classe energetique : {self.label_energie}")
        if self.type_vmc:
            labels = dict(self._fields['type_vmc'].selection)
            lines.append(f"VMC : {labels.get(self.type_vmc, self.type_vmc)}")
        if self.surface_capteurs:
            lines.append(f"Surface capteurs : {self.surface_capteurs} m2")
        if self.nb_equipements:
            lines.append(f"Nb equipements : {self.nb_equipements}")
        if self.epaisseur_isolant:
            lines.append(f"Epaisseur isolant : {self.epaisseur_isolant} mm")
        if self.volume_ballon:
            lines.append(f"Volume ballon : {self.volume_ballon} L")
        if self.secteur_activite:
            labels = dict(self._fields['secteur_activite'].selection)
            lines.append(f"Secteur activite : {labels.get(self.secteur_activite, self.secteur_activite)}")
        if self.ug:
            lines.append(f"Ug : {self.ug} W/m2.K")
        if self.type_serre:
            labels = dict(self._fields['type_serre'].selection)
            lines.append(f"Type serre : {labels.get(self.type_serre, self.type_serre)}")
        if self.thermicite:
            labels = dict(self._fields['thermicite'].selection)
            lines.append(f"Thermicite : {labels.get(self.thermicite, self.thermicite)}")
        if self.delta_t:
            lines.append(f"Delta T : {self.delta_t} C")
        if self.type_condensation:
            labels = dict(self._fields['type_condensation'].selection)
            lines.append(f"Condensation : {labels.get(self.type_condensation, self.type_condensation)}")
        if self.mode_fonctionnement:
            lines.append(f"Mode fonctionnement : {self.mode_fonctionnement}")
        return '\n'.join(lines)

    def action_ouvrir_produit(self):
        """Ouvre la fiche du produit lié dans une nouvelle fenêtre."""
        self.ensure_one()
        product = self.product_line_id.product_id if self.product_line_id else None
        if not product:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': product.display_name,
            'res_model': 'product.product',
            'res_id': product.id,
            'views': [(False, 'form')],
            'target': 'new',
        }
