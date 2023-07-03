import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo.tools.translate import _
from odoo.exceptions import except_orm
from odoo import models, fields, api
from odoo.tools.misc import str2bool, xlwt
from xlwt import easyxf

try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter

try:
    from StringIO import StringIO 
except ImportError:
    from io import StringIO,BytesIO  


class account_move_line_in_report(models.TransientModel):
    _name = 'account.move.line.in.report.wizard'
    _description = 'account_move_line_report'

    start_date = fields.Date(required=True, default=fields.Date.today())
    end_date = fields.Date(required=True)

    @api.model
    def get_lines(self):
        domain = [
            ('date', '>=', self.start_date),
            ('date', '<=', self.end_date),
            ('journal_id.type', '!=', 'sale'),
            ('move_id.state', '=', 'posted')
        ]
        move_line_obj = self.env['account.move.line']
        move_lines = move_line_obj.search(domain)
        move_line_data = []
        for line in move_lines:
            taxAudit = 0.0
            currency = line.company_id.currency_id
            for tag in line.tax_tag_ids:
                caba_origin_inv_type = line.move_id.type
                caba_origin_inv_journal_type = line.journal_id.type

                if line.move_id.tax_cash_basis_rec_id:
                    # Cash basis entries are always treated as misc operations, applying the tag sign directly to the balance
                    type_multiplicator = 1
                else:
                    type_multiplicator = (line.journal_id.type == 'sale' and -1 or 1) * (line._get_refund_tax_audit_condition(line) and -1 or 1)

                taxAudit = type_multiplicator * (tag.tax_negate and -1 or 1) * line.balance
            if not taxAudit:
                continue
            move_line_data.append({
                'partner_name': line.partner_id.x_studio_arabic_name or '',
                'city': line.partner_id.city or '',
                'tax_no': line.partner_id.vat or '',
                'date': str(line.move_id.invoice_date) or '',
                'journal_type': 'purchase_journal',
                'invoice_type': 'purchase',
                'journal_id': line.journal_id.name or '',
                'journal_entry': line.move_id.name or '',
                'ref': line.ref or '',
                'label': line.name or '',
                'tax_base_amount': line.tax_base_amount or 0.0,
                'tax_audit': float(taxAudit) or 0.0,
                'total_invoice': line.tax_base_amount + taxAudit
            })
        return move_line_data

    def _print_exp_report(self, data):
        res = {}
        import base64
        filename = 'Vat In Report.xls'
        workbook = xlwt.Workbook(encoding="UTF-8")
        worksheet = workbook.add_sheet('Vat In Report')
        
        header_style = easyxf('font:height 200;pattern: pattern solid, fore_colour gray25; align: horiz center;font: color black; font:bold True;' "borders: top thin,left thin,right thin,bottom thin")
        font_bold = easyxf('font:height 200;pattern: pattern solid, fore_colour gray25; align: horiz center;font: color black; font:bold True;' "borders: top thin,left thin,right thin,bottom thin")

        company_id = self.env.user.company_id

        worksheet.write_merge(0, 0, 6, 8, company_id.name, font_bold)
        worksheet.write_merge(1, 1, 0, 8,  str(self.start_date) + ' to ' + str(self.end_date), font_bold)

        datecombo = self.start_date.strftime("%b") + '-' + self.end_date.strftime("%b") + '-' + str(self.end_date.year)

        for i in range(0,13):
            worksheet.col(i).width = 150 * 30

        worksheet.col(8).width = 300 * 30

        row = 2
        col = 0
        worksheet.write(row, col, 'Total Invoice', font_bold)
        col += 1
        worksheet.write(row, col, 'Tax Audit String', font_bold)
        col += 1
        worksheet.write(row, col, 'Base Amount', font_bold)
        col += 1
        worksheet.write(row, col, 'Label', font_bold)
        col += 1
        worksheet.write(row, col, 'Reference', font_bold)
        col += 1
        worksheet.write(row, col, 'Journal Entry', font_bold)
        col += 1
        worksheet.write(row, col, 'Journal', font_bold)
        col += 1
        worksheet.write(row, col, 'Journal Type', font_bold)
        col += 1
        worksheet.write(row, col, 'Type Invoice', font_bold)
        col += 1
        worksheet.write(row, col, 'Date', font_bold)
        col += 1
        worksheet.write(row, col, 'Tax Id', font_bold)
        col += 1
        worksheet.write(row, col, 'City', font_bold)
        col += 1
        worksheet.write(row, col, 'Partner', font_bold)
        col += 1

        row += 1
        line_details = self.get_lines()
        i = row
        tax_base_amount = 0.0
        total_invoice = 0.0
        tax_audit = 0.0
        if line_details:
            style_3 = easyxf('font:height 200; align: horiz right;')
            style_3.num_format_str = '0.00'
            for line in line_details:
                tax_base_amount += line.get('tax_base_amount')
                total_invoice += line.get('total_invoice')
                tax_audit += line.get('tax_audit')

                col = 0
                worksheet.write(i, col, line.get('total_invoice'), style_3)
                col += 1
                worksheet.write(i, col, line.get('tax_audit'), style_3)
                col += 1
                worksheet.write(i, col, line.get('tax_base_amount', ''), style_3)
                col += 1
                worksheet.write(i, col, line.get('label'))
                col += 1
                worksheet.write(i, col, line.get('ref'))
                col += 1
                worksheet.write(i, col, line.get('journal_entry'))
                col += 1
                worksheet.write(i, col, line.get('journal_id'))
                col += 1
                worksheet.write(i, col, line.get('journal_type'))
                col += 1
                worksheet.write(i, col, line.get('invoice_type'))
                col += 1
                worksheet.write(i, col, line.get('date'))
                col += 1
                worksheet.write(i, col, line.get('tax_no'))
                col += 1
                worksheet.write(i, col, line.get('city'))
                col += 1
                worksheet.write(i, col, line.get('partner_name'))
                col += 1
                i += 1
        else:
            i += 1

        foolter_style_1 = easyxf('font:height 200; align: horiz right; font:bold True;')
        foolter_style_1.num_format_str = '0.00'
        col = 0
        worksheet.write(i, col, total_invoice, foolter_style_1)
        col += 1
        worksheet.write(i, col, tax_audit, foolter_style_1)
        col += 1
        worksheet.write(i, col, tax_base_amount, foolter_style_1)

        import io
        fp = io.BytesIO()
        workbook.save(fp)
        export_id = self.env['download.accountml.wizard.report.in'].create(
            {'excel_file': base64.encodestring(fp.getvalue()),
             'file_name': filename},)
        fp.close()
        
        return {
            'view_mode': 'form',
            'res_id': export_id.id,
            'res_model': 'download.accountml.wizard.report.in',
            'view_type': 'form',
            'type': 'ir.actions.act_window',
            'context': self._context,
            'target': 'new',
            
        }

    def generate_excel_report(self):
        data = {}
        data['ids'] = self._context.get('active_ids', [])
        data['model'] = self._context.get('active_model', 'ir.ui.menu')
        for record in self:
            data['form'] = record.read(['start_date', 'end_date'])[0]
        return self._print_exp_report(data)


class DownloadAccountMoveLineDownloadIn(models.TransientModel):
    _name = "download.accountml.wizard.report.in"
    _description = "download.accountml.wizard.report.in"
    
    excel_file = fields.Binary('Excel Report')
    file_name = fields.Char('Excel File', size=64)