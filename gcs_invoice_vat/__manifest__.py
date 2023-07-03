{
    'name': 'Electronic invoice KSA- GCS VAT Invoice in odoo 16',
    'version': '16.1.1.1',
    'sequence':1,
    'category': 'Accounting',
    'summary': 'Electronic invoice KSA - Sale, Purchase, Invoice, Credit Note, Debit Note | Invoice based on TLV Base64 string QR Code | Saudi Electronic Invoice with Base64 TLV QRCode',
    
    'description': """
     Electronic invoice KSA - Sale, Purchase, Invoice, Credit Note, Debit Note | Invoice based on TLV Base64 string QR Code | Saudi Electronic Invoice with Base64 TLV QRCode
     Using this module you can print Saudi electronic invoice for Sale, Purchase, Invoice and  POS Order Invoice Report.
     According to Saudi Government QR code with Display Saudi Tax detials, Customer Name, Customer Vat, Invoice Date, Total of VAT, Totaol of Amount.
     """,
    "author" : "odoobridge",
    "email": 'odoobridge@gmail.com',
    "license": 'OPL-1',
    'depends': ['sale_management', 'account'],
    #'depends': ['sale_management','purchase', 'account', 'subcontract_agreement', 'point_of_sale'],

    'data': [
        'security/ir.model.access.csv',
        'report/vat_invoice_report_print.xml',
        'report/vat_report_action_call.xml',
       # 'report/vat_sale_report_print.xml',
       # 'report/vat_purchase_report_print.xml',
       # 'report/simpli_vat_invoice_report.xml',
       # 'report/simpli_vat_invoice_report_pos.xml',
        'views/sale_purchase_invoice_view.xml',
      #  'report/invoice_default_attach.xml',
        'wizard/vat_out_report_view.xml',
        'wizard/vat_in_report_view.xml',
    ],

    'assets': {
        'web.assets_common': [
            'gcs_invoice_vat/static/src/css/style.css',
        ],
        'web.assets_frontend': [
            'gcs_invoice_vat/static/src/css/style.css',
        ],
    },

    'price': 40,
    'currency': 'EUR',
    #"live_test_url" : "https://youtu.be/emL5ahmrBFI",   
    # Old Live Link
    # "live_test_url" : "https://youtu.be/foB1JwMIIC8", 
    "images": ['static/description/logo.gif'],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': True,
}

