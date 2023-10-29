{
    'name': "Electronic Invoice - Accounting",
    'author': "TBS",
    'category': 'accounting',
    'version': '1.0',
    'license': 'AGPL-3',
    'summary': 'Electronic Invoice Tax - Accounting',
    'description': 'Electronic Invoice Tax - Accounting',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
        'reports/invoice_qr_report.xml',
    ],
}
