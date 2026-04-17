{
    'name': 'Calcul des primes CEE',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'Calcul automatique des primes CEE sur les devis IBATIX',
    'author': 'ibatix',
    'depends': [
        'sale',
        'ibatix_champs',
        'ibatix_intelligence',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_views.xml',
        'views/wizard_cee_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
