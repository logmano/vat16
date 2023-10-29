import qrcode
import base64
from io import BytesIO
from odoo import models, api, fields, _
import binascii
from odoo.exceptions import UserError, ValidationError
from .qr_generator import generateQrCode
from odoo.tools import html2plaintext

import logging


_logger = logging.getLogger(__name__)

######################################################################################################################
######################################################################################################################


class invoiceQrFields(models.Model):
    _name = 'invoice.qr.fields'
    _description = "Invoice QR-Fields"
    _order = 'QR Fields'

    sequence = fields.Integer()
    field_id = fields.Many2one('ir.model.fields',
                               domain=[('model_id.model', '=', 'account.move'),
                                       ('ttype', 'not in', ['many2many', 'one2many', 'binary'])])
    company_id = fields.Many2one('res.company')

######################################################################################################################
######################################################################################################################


class ResCompany(models.Model):
    _inherit = 'res.company'

    invoice_qr_type = fields.Selection([('by_url', 'Invoice Url'), ('by_info', 'Invoice Text Information')], default='by_url', required=True)
    invoice_field_ids = fields.One2many('invoice.qr.fields', 'company_id', string="Invoice Fields")

    # @api.constrains('invoice_qr_type', 'invoice_field_ids')
    # def check_invoice_field_ids(self):
    #     for rec in self:
    #         if rec.invoice_qr_type == 'by_info' and not rec.invoice_field_ids:
    #             raise ValidationError(_("Please Add Invoice Field's"))

######################################################################################################################
######################################################################################################################


class AccountMoveLineInherit(models.Model):
    _inherit = 'account.move.line'

    tax_amount = fields.Float(string="Tax Amount", compute="_compute_tax_amount")

    @api.depends('tax_ids', 'price_unit', 'quantity')
    def _compute_tax_amount(self):
        for line in self:
            if line.tax_ids:
                line.tax_amount = line.price_total - line.price_subtotal
            else:
                line.tax_amount = 0.0

######################################################################################################################
######################################################################################################################


class AccountMoveInherit(models.Model):
    _inherit = 'account.move'

    qr_code = fields.Binary(string="QR Code", copy=False, store=True)

    @api.onchange('partner_id')
    def _onchange_partner_warning_vat(self):
        if not self.partner_id:
            return
        partner = self.partner_id
        warning = {}
        if partner.company_type == 'company' and not partner.vat:
            title = ("Warning for %s") % partner.name
            message = _("Please add VAT ID for This Partner '%s' !") % (partner.name)
            warning = {
                'title': title,
                'message': message,
            }
        if warning:
            res = {'warning': warning}
            return res

    def _string_to_hex(self, value):
        if value:
            string = str(value)
            string_bytes = string.encode("UTF-8")
            encoded_hex_value = binascii.hexlify(string_bytes)
            hex_value = encoded_hex_value.decode("UTF-8")
            return hex_value

    def _get_hex(self, tag, length, value):
        if tag and length and value:
            hex_string = self._string_to_hex(value)
            length = int(len(hex_string) / 2)
            conversion_table = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c', 'd', 'e', 'f']
            hexadecimal = ''
            while (length > 0):
                remainder = length % 16
                hexadecimal = conversion_table[remainder] + hexadecimal
                length = length // 16
            if len(hexadecimal) == 1:
                hexadecimal = "0" + hexadecimal
            return tag + hexadecimal + hex_string

    def get_qr_code_data(self):
        self.ensure_one()
        if self.move_type in ('out_invoice', 'out_refund'):
            sellername = str(self.company_id.name)
            seller_vat_no = self.company_id.vat or ''
            if self.partner_id.company_type == 'company':
                customer_name = self.partner_id.name
                customer_vat = self.partner_id.vat
        else:
            sellername = str(self.partner_id.name)
            seller_vat_no = self.partner_id.vat
        seller_hex = self._get_hex("01", "0c", sellername)
        vat_hex = self._get_hex("02", "0f", seller_vat_no) or ""
        time_stamp = str(self.invoice_date or self.create_date)
        date_hex = self._get_hex("03", "14", time_stamp)
        total_with_vat_hex = self._get_hex("04", "0a", str(round(self.amount_total, 2))) or 0
        total_vat_hex = self._get_hex("05", "09", str(round(self.amount_tax, 2))) or 0
        qr_hex = seller_hex + vat_hex + date_hex + total_with_vat_hex + total_vat_hex
        encoded_base64_bytes = base64.b64encode(bytes.fromhex(qr_hex)).decode()
        return encoded_base64_bytes

    def _get_qr_image(self):
        self.ensure_one()
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(self.get_qr_code_data())
        qr.make(fit=True)
        img = qr.make_image()
        temp = BytesIO()
        img.save(temp, format="PNG")
        qr_image = base64.b64encode(temp.getvalue())
        return qr_image

    # @api.onchange('invoice_line_ids', 'partner_id')
    def generate_qr_code(self):
        for rec in self:
            qr_image = rec._get_qr_image()
            rec.qr_code = qr_image

    # def _generate_qr_code(self):
    #     for rec in self:
    #         company_id = rec.company_id or self.env.company
    #         qr_info = ''
    #         if company_id.invoice_qr_type != 'by_info':
    #             qr_info = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
    #             qr_info += rec.get_portal_url()
    #         else:
    #             if company_id.invoice_field_ids:
    #                 dict_result = {}
    #                 for ffild in company_id.invoice_field_ids.mapped('field_id'):
    #                     if ffild.ttype == 'many2one':
    #                         dict_result[ffild.field_description] = rec[ffild.name].display_name
    #                     else:
    #                         dict_result[ffild.field_description] = rec[ffild.name]
    #                 for key, value in dict_result.items():
    #                     if str(key).__contains__('Partner') or str(key).__contains__(_('Partner')):
    #                         if rec.move_type in ['out_invoice', 'out_refund']:
    #                             key = str(key).replace(_('Partner'), _('Customer'))
    #                         elif rec.move_type in ['in_invoice', 'in_refund']:
    #                             key = str(key).replace(_('Partner'), _('Vendor'))
    #                     qr_info += f"{key} : {value} <br/>"
    #                 qr_info = html2plaintext(qr_info)
    #         rec.qr_code = generateQrCode.generate_qr_code(qr_info)
