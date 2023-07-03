# -*- coding: utf-8 -*-

from odoo import api, fields, models, _, Command
import qrcode
import base64
import io
from odoo import http
from num2words import num2words
from odoo.tools.misc import formatLang, format_date, get_lang


class AccountMove(models.Model):
    _inherit = 'account.move'

    date_due = fields.Date('Date Due')
    invoice_date_supply = fields.Date('Date Of Supply')
    advance_payment = fields.Float('Advance Payment Deduction %')
    retainsion_amount = fields.Float('Retention %')
    perform_band = fields.Float('Performance Bond')
    back_charge = fields.Float('Back Charge')
    saudization_deduction = fields.Float('Saudization Deduction')
    contrac_no = fields.Char('Contract number')
    subject_name = fields.Char('Subject')
    po_number = fields.Char('PO number')
    project_name = fields.Char('Project Name')
    vendor_num = fields.Char('Vendor No.')
    amount_word_arabic = fields.Char('Arabic Amount')
    report_type = fields.Selection([
        ('General Report', 'General Report'),
        ('Sadara Report', 'Sadara Report'),
        ('Aramco', 'Aramco Report')
        # ('Sub Contract Report', 'Sub Contract Report')
        ], default="General Report", string='Report Type')

    total_with_vat = fields.Monetary(compute='_compute_cal_move_fields', string='TOTAL Exclude VAT', currency_field='currency_id', store=True)
    advance_payment_amount = fields.Monetary(compute='_compute_cal_move_fields', string='Advance Payment', currency_field='currency_id', store=True)
    taxable_total_amount = fields.Monetary(compute='_compute_cal_move_fields', string='Taxable Amount', currency_field='currency_id', store=True)
    vat_15 = fields.Monetary(compute='_compute_cal_move_fields', string='VAT 15%', currency_field='currency_id', store=True)
    amount_include_vat = fields.Monetary(compute='_compute_cal_move_fields', string='Amount including VAT%', currency_field='currency_id', store=True)
    retainsion_amount_form = fields.Monetary(compute='_compute_cal_move_fields', string='Retention dedection', currency_field='currency_id', store=True)
    perform_band_form = fields.Monetary(compute='_compute_cal_move_fields', string='Performance Bond ', currency_field='currency_id', store=True)
    back_charge_form = fields.Monetary(compute='_compute_cal_move_fields', string='Back Charge ', currency_field='currency_id', store=True)
    saudization_deduction_form = fields.Monetary(compute='_compute_cal_move_fields', string='Saudization Deduction ', currency_field='currency_id', store=True)
    net_total_calc = fields.Monetary(compute='_compute_cal_move_fields', string='Net Total Amount ( Amount Due )', currency_field='currency_id', store=True)
    subcontract_invoice = fields.Boolean('Subcontract Invoice?')
    check_move_post = fields.Boolean(compute='_compute_check_move_post')
    check_move_set_to_draft = fields.Boolean(compute='_compute_check_move_post')

    def _compute_check_move_post(self):
        for rec in self:
            if rec.move_type in ['out_invoice', 'in_invoice', 'entry']:
                if self.env.user.has_group('gcs_invoice_vat.group_access_move_invoice_post') and rec.move_type == 'out_invoice' and rec.state == 'draft':
                    rec.check_move_post = True
                elif self.env.user.has_group('gcs_invoice_vat.group_access_move_bill_post') and rec.move_type == 'in_invoice' and rec.state == 'draft':
                    rec.check_move_post = True
                elif self.env.user.has_group('gcs_invoice_vat.group_access_move_je_post') and rec.move_type == 'entry' and rec.state == 'draft':
                    rec.check_move_post = True
                else:
                    rec.check_move_post = False
            else:
                if rec.state == 'draft':
                    rec.check_move_post = True
                else:
                    rec.check_move_post = False
            if rec.move_type in ['out_invoice', 'out_refund'] and self.env.user.has_group('gcs_invoice_vat.group_access_draft') and rec.state != 'draft':
                rec.check_move_set_to_draft = True
            elif rec.move_type in ['in_invoice', 'in_refund'] and self.env.user.has_group('gcs_invoice_vat.group_access_draft_bills') and rec.state != 'draft':
                rec.check_move_set_to_draft = True
            elif rec.move_type == 'entry' and self.env.user.has_group('gcs_invoice_vat.group_access_draft_je') and rec.state != 'draft':
                rec.check_move_set_to_draft = True
            else:
                rec.check_move_set_to_draft = False

    def action_post(self):
        res = super(AccountMove, self.with_context(check_move_validity=False)).action_post()
        self.update_lines()
        return res

    def update_lines(self):
        self.with_context({'check_move_validity': False, 'skip_update': True, 'force_delete': True}).line_ids -= self.line_ids.filtered(lambda line_id: line_id.line_type in ['advance_payment', 'back_charge', 'retention', 'performance_bond', 'saudization_deduction'])
        if self.advance_payment_amount:
            self.create_advance_payment()
        if self.back_charge_form:
            self.create_back_charge()
        if self.retainsion_amount_form:
            self.create_Retention()
        if self.perform_band_form:
            self.create_Performance()
        if self.saudization_deduction_form:
            self.create_Saudization()
        self._cr.commit()
        # self.with_context({'check_move_validity': False, 'skip_update': True}).line_ids -= self.line_ids.filtered(lambda l: not l.credit and not l.debit and  l.line_type in ['advance_payment', 'back_charge', 'retention', 'performance_bond', 'saudization_deduction'] and l.line_type != 'default')

    @api.depends('subcontract_invoice', 'perform_band', 'advance_payment', 'retainsion_amount', 
        'invoice_line_ids', 'back_charge', 'saudization_deduction', 'invoice_line_ids.product_id', 
        'invoice_line_ids.quantity', 'invoice_line_ids.price_unit', 'invoice_line_ids.price_subtotal', 
        'state')
    def _compute_cal_move_fields(self):
        for rec in self:
            calc_advance_pay = round(rec.amount_untaxed * rec.advance_payment / 100, 2)
            retencion_calc = round(rec.amount_untaxed * rec.retainsion_amount / 100, 2)
            perform_band = round(rec.perform_band, 2)
            back_charge_form = round(rec.back_charge, 2)
            saudization_deduction_form = round(rec.saudization_deduction, 2)

            tax_total = 0
            line_tax_total = 0
            for line in rec.invoice_line_ids:
                for l in line.tax_ids:
                    tax_total += line.price_subtotal * l.amount / 100
                    line_tax_total += l.amount

            taxable_total_amount = round(rec.amount_untaxed - (calc_advance_pay + rec.back_charge), 2)
            # taxable_total_amount = rec.amount_total - tax_total - calc_advance_pay
            vat_amt_calc = 0.0
            if tax_total or line_tax_total and (calc_advance_pay or back_charge_form):
                vat_amt_calc = round(taxable_total_amount * 15 / 100, 2)
            if not (calc_advance_pay or back_charge_form):
                vat_amt_calc = rec.amount_tax
            rec.total_with_vat = rec.amount_untaxed #+ rec.amount_tax
            rec.advance_payment_amount = calc_advance_pay
            rec.taxable_total_amount = taxable_total_amount
            rec.vat_15 = vat_amt_calc
            amt_incl_vat = taxable_total_amount + vat_amt_calc
            rec.amount_include_vat = amt_incl_vat
            rec.retainsion_amount_form = retencion_calc
            rec.perform_band_form = perform_band
            rec.back_charge_form = back_charge_form
            rec.saudization_deduction_form = saudization_deduction_form
            rec.net_total_calc = round(amt_incl_vat - retencion_calc - perform_band - rec.saudization_deduction, 2)

    def fixed_label_name(self):
        for line_id in self.line_ids:
            if line_id.name and '_<NewId'in line_id.name:
                line_id.name = line_id.name.split('_<NewId')[0]

    def create_advance_payment(self):
        create_method = self.env['account.move.line'].with_context(check_move_validity=False).create
        if self.move_type in ['out_invoice', 'in_refund'] and self.amount_untaxed:
            line_payables = self.line_ids.filtered(lambda lines: lines.account_id.account_type == 'asset_receivable')
            line_payables = line_payables and line_payables[0]
            account_id = self.partner_id.advance_account.id
            advance_amount = self.advance_payment_amount
            advance_payment_name = 'Advance Payment ' + str(self.advance_payment) + '%'
            candidate = create_method({
                'name': advance_payment_name,
                'debit': advance_amount,
                'amount_currency': advance_amount,
                'credit': 0,
                'quantity': 1.0,
                'date_maturity': fields.Date.context_today(self),
                'move_id': self.id,
                'account_id': account_id,
                'partner_id': self.commercial_partner_id.id,
                'line_type': 'advance_payment',
                'currency_id': self.currency_id.id,
                'display_type' : 'others',
                'company_id': self.company_id.id,
            })
            if self.vat_15:
                line_tax_ids = self.line_ids.filtered(lambda lines: lines.tax_line_id)
                if line_tax_ids:
                    line_tax_ids[0].with_context({'check_move_validity': False, 'skip_update': True}).write({'credit': self.vat_15})
            line_payables.with_context({'check_move_validity': False, 'skip_update': True}).write({'debit': self.net_total_calc})

    def create_back_charge(self):
        print("11111111create_back_charge111111111")
        create_method = self.env['account.move.line'].with_context(check_move_validity=False).create
        if self.move_type in ['out_invoice', 'in_refund'] and self.amount_untaxed:
            line_payables = self.line_ids.filtered(lambda lines: lines.account_id.account_type == 'asset_receivable')
            line_payables = line_payables and line_payables[0]
            account_id = self.partner_id.back_charge_account_id.id
            advance_amount = round(self.back_charge_form, 2)
            advance_payment_name = 'Back Charge'
            candidate = create_method({
                'name': advance_payment_name,
                'debit': advance_amount,
                'amount_currency': advance_amount,
                'credit': 0,
                'quantity': 1.0,
                'date_maturity': fields.Date.context_today(self),
                'move_id': self.id,
                'currency_id': self.currency_id.id,
                'display_type' : 'others',
                'company_id': self.company_id.id,
                'account_id': account_id,
                'line_type': 'back_charge'
            })
            if self.vat_15:
                print("=111111111111111111111==self.vat_15==", self.vat_15)
                line_tax_ids = self.line_ids.filtered(lambda lines: lines.tax_line_id)
                if line_tax_ids:
                    line_tax_ids[0].with_context({'check_move_validity': False, 'skip_update': True}).write({'credit': self.vat_15})
            line_payables.with_context({'check_move_validity': False, 'skip_update': True}).write({'debit': self.net_total_calc})

    def create_Retention(self):
        create_method = self.env['account.move.line'].with_context(check_move_validity=False).create
        if self.move_type in ['out_invoice', 'in_refund'] and self.amount_untaxed:
            line_payables = self.line_ids.filtered(lambda lines: lines.account_id.account_type == 'asset_receivable')
            line_payables = line_payables and line_payables[0]
            account_id = self.partner_id.retention_account.id
            advance_amount = self.retainsion_amount_form
            advance_payment_name = 'Retention ' + str(self.retainsion_amount) + '%'
            candidate = create_method({
                'name': advance_payment_name,
                'debit': advance_amount,
                'credit': 0,
                'quantity': 1.0,
                'date_maturity': fields.Date.context_today(self),
                'move_id': self.id,
                'account_id': account_id,
                'partner_id': self.partner_id.id,
                'line_type': 'retention',
                'currency_id': self.currency_id.id,
                'display_type' : 'others',
                'company_id': self.company_id.id,
            })

            if self.vat_15:
                print("=111111111111111111111==self.vat_15==", self.vat_15)
                line_tax_ids = self.line_ids.filtered(lambda lines: lines.tax_line_id)
                if line_tax_ids:
                    line_tax_ids[0].with_context({'check_move_validity': False, 'skip_update': True}).write({'credit': self.vat_15})
            line_payables.with_context({'check_move_validity': False, 'skip_update': True}).write({'debit': self.net_total_calc})

    def create_Performance(self):
        create_method = self.env['account.move.line'].with_context(check_move_validity=False).create
        if self.move_type in ['out_invoice', 'in_refund'] and self.amount_untaxed:
            line_payables = self.line_ids.filtered(lambda lines: lines.account_id.account_type == 'asset_receivable')
            line_payables = line_payables and line_payables[0]
            account_id = account_id = self.partner_id.performance_bond_account.id or self.journal_id.default_debit_account_id.id
            advance_amount = self.perform_band
            advance_payment_name = 'Performance Bond '
            candidate = create_method({
                'name': advance_payment_name,
                'debit': advance_amount,
                'credit': 0,
                'quantity': 1.0,
                'date_maturity': fields.Date.context_today(self),
                'move_id': self.id,
                'account_id': account_id,
                'partner_id': self.partner_id.id,
                'line_type': 'performance_bond',
                'currency_id': self.currency_id.id,
                'display_type' : 'others',
                'company_id': self.company_id.id,
            })

            if self.vat_15:
                print("=111111111111111111111==self.vat_15==", self.vat_15)
                line_tax_ids = self.line_ids.filtered(lambda lines: lines.tax_line_id)
                if line_tax_ids:
                    line_tax_ids[0].with_context({'check_move_validity': False, 'skip_update': True}).write({'credit': self.vat_15})
            line_payables.with_context({'check_move_validity': False, 'skip_update': True}).write({'debit': self.net_total_calc})

    def create_Saudization(self):
        create_method = self.env['account.move.line'].with_context(check_move_validity=False).create
        if self.move_type in ['out_invoice', 'in_refund'] and self.amount_untaxed:
            line_payables = self.line_ids.filtered(lambda lines: lines.account_id.account_type == 'asset_receivable')
            line_payables = line_payables and line_payables[0]
            account_id = self.partner_id.sau_deduction_account_id.id
            advance_amount = round(self.saudization_deduction_form)
            advance_payment_name = 'Saudization Deduction'
            candidate = create_method({
                'name': advance_payment_name,
                'debit': advance_amount,
                'credit': 0,
                'quantity': 1.0,
                'date_maturity': fields.Date.context_today(self),
                'move_id': self.id,
                'currency_id': self.currency_id.id if self.currency_id != self.company_id.currency_id else False,
                'account_id': account_id,
                'partner_id': self.partner_id.id,
                'line_type': 'saudization_deduction',
                'currency_id': self.currency_id.id,
                'display_type' : 'others',
                'company_id': self.company_id.id,
            })
            if self.vat_15:
                line_tax_ids = self.line_ids.filtered(lambda lines: lines.tax_line_id)
                if line_tax_ids:
                    line_tax_ids[0].with_context({'check_move_validity': False, 'skip_update': True}).write({'credit': self.vat_15})
            line_payables.with_context({'check_move_validity': False, 'skip_update': True}).write({'debit': self.net_total_calc})

    def get_product_arabic_name(self,pid):
        # translation = self.env['ir.translation'].search([
        #     ('name','=','product.product,name'),('state','=','translated'),
        #     ('res_id','=',pid)])
        # if translation :
        #     return translation.value
        # else: 
        #     product = self.env['product.product'].browse(int(pid))
        #     translation = self.env['ir.translation'].search([
        #         ('name','=','product.product,name'),('state','=','translated'),
        #         ('res_id','=',product.product_tmpl_id.id)])
        #     if translation :
        #         return translation.value
        return _(pid.display_name)

    def amount_word(self, amount):
        language = self.partner_id.lang or 'en'
        language_id = self.env['res.lang'].search([('code', '=', 'ar_001')])
        if language_id:
            language = language_id.iso_code
        amount_str =  str('{:2f}'.format(amount))
        amount_str_splt = amount_str.split('.')
        before_point_value = amount_str_splt[0]
        after_point_value = amount_str_splt[1][:2]           
        before_amount_words = num2words(int(before_point_value),lang=language)
        after_amount_words = num2words(int(after_point_value),lang=language)
        amount = before_amount_words + ' ' + after_amount_words
        return amount

    def amount_total_words(self, amount):
        words_amount = self.currency_id.amount_to_text(amount)
        return words_amount

    @api.model
    def get_qr_code(self):

        def get_qr_encoding(tag, field):
            company_name_byte_array = field.encode('UTF-8')
            company_name_tag_encoding = tag.to_bytes(length=1, byteorder='big')
            company_name_length_encoding = len(company_name_byte_array).to_bytes(length=1, byteorder='big')
            return company_name_tag_encoding + company_name_length_encoding + company_name_byte_array

        qr_code_str = ''
        seller_name_enc = get_qr_encoding(1, self.company_id.display_name)
        company_vat_enc = get_qr_encoding(2, self.company_id.vat or '')
        time_sa = fields.Datetime.context_timestamp(self.with_context(tz='Asia/Riyadh'), self.create_date)
        timestamp_enc = get_qr_encoding(3, time_sa.isoformat())

        # tax_total = 0.0
        # for l in self.invoice_line_ids:
        #     for t in l.tax_ids:
        #         tax_total += l.price_subtotal * t.amount / 100

        # calc_advance_pay = 0.0
        # if self.advance_payment and self.amount_untaxed:
        #     calc_advance_pay = self.amount_untaxed * self.advance_payment/100

        # taxable_total_amount = self.amount_total - tax_total - calc_advance_pay
        # vat_amt_calc = 0.0
        # amt_incl_vat = 0.0
        # if taxable_total_amount:
        #     vat_amt_calc = taxable_total_amount * 15/100
        #     amt_incl_vat = taxable_total_amount + vat_amt_calc
        # invoice_total_enc = get_qr_encoding(4, str(amt_incl_vat))
        # total_vat_enc = get_qr_encoding(5, str(self.currency_id.round(vat_amt_calc)))


        invoice_total_enc = get_qr_encoding(4, str(self.amount_include_vat))
        total_vat_enc = get_qr_encoding(5, str(self.currency_id.round(self.vat_15)))

        str_to_encode = seller_name_enc + company_vat_enc + timestamp_enc + invoice_total_enc + total_vat_enc
        qr_code_str = base64.b64encode(str_to_encode).decode('UTF-8')
        return qr_code_str

    def action_invoice_sent(self):
        """ Open a window to compose an email, with the edi invoice template
            message loaded by default
        """
        self.ensure_one()
        template = self.env.ref('gcs_invoice_vat.email_template_edi_invoice_etir', False)
        lang = get_lang(self.env)
        if template and template.lang:
            lang = template._render_template(template.lang, 'account.move', self.id)
        else:
            lang = lang.code
        compose_form = self.env.ref('account.account_invoice_send_wizard_form', raise_if_not_found=False)
        ctx = dict(
            default_model='account.move',
            default_res_id=self.id,
            # For the sake of consistency we need a default_res_model if
            # default_res_id is set. Not renaming default_model as it can
            # create many side-effects.
            default_res_model='account.move',
            default_use_template=bool(template),
            default_template_id=template and template.id or False,
            default_composition_mode='comment',
            mark_invoice_as_sent=True,
            custom_layout="mail.mail_notification_paynow",
            model_description=self.with_context(lang=lang).type_name,
            force_email=True
        )
        return {
            'name': _('Send Invoice'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.invoice.send',
            'views': [(compose_form.id, 'form')],
            'view_id': compose_form.id,
            'target': 'new',
            'context': ctx,
        }


    # def action_invoice_sent(self):
    #     """ Open a window to compose an email, with the edi invoice template
    #         message loaded by default
    #     """
    #     self.ensure_one()
    #     template = self.env.ref('gcs_invoice_vat.email_template_edi_invoice_etir', False)
    #     compose_form = self.env.ref('account.account_invoice_send_wizard_form', False)
    #     # have model_description in template language
    #     lang = self.env.context.get('lang')
    #     if template and template.lang:
    #         lang = template._render_template(template.lang, 'account.move', self.id)
    #     self = self.with_context(lang=lang)
    #     TYPES = {
    #         'out_invoice': _('Invoice'),
    #         'in_invoice': _('Vendor Bill'),
    #         'out_refund': _('Credit Note'),
    #         'in_refund': _('Vendor Credit note'),
    #     }
    #     ctx = dict(
    #         default_model='account.move',
    #         default_res_id=self.id,
    #         default_use_template=bool(template),
    #         default_template_id=template and template.id or False,
    #         default_composition_mode='comment',
    #         mark_invoice_as_sent=True,
    #         model_description=TYPES[self.move_type],
    #         custom_layout="mail.mail_notification_paynow",
    #         force_email=True
    #     )
    #     return {
    #         'name': _('Send Invoice'),
    #         'type': 'ir.actions.act_window',
    #         'view_type': 'form',
    #         'view_mode': 'form',
    #         'res_model': 'account.move.send',
    #         'views': [(compose_form.id, 'form')],
    #         'view_id': compose_form.id,
    #         'target': 'new',
    #         'context': ctx,
    #     }

    # @api.returns('self', lambda value: value.id)
    # def copy(self, default=None):
    #     print("==self==", self)
    #     print("==default==", default)
    #     jlkjlj
    #     # default = dict(default or {})
    #     # if default.get('code', False):
    #     #     return super(AccountAccount, self).copy(default)
    #     # try:
    #     #     default['code'] = (str(int(self.code) + 10) or '').zfill(len(self.code))
    #     #     default.setdefault('name', _("%s (copy)") % (self.name or ''))
    #     #     while self.env['account.account'].search([('code', '=', default['code']),
    #     #                                               ('company_id', '=', default.get('company_id', False) or self.company_id.id)], limit=1):
    #     #         default['code'] = (str(int(default['code']) + 10) or '')
    #     #         default['name'] = _("%s (copy)") % (self.name or '')
    #     # except ValueError:
    #     #     default['code'] = _("%s (copy)") % (self.code or '')
    #     #     default['name'] = self.name
    #     return super(AccountMove, self).copy(default)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    display_type = fields.Selection(
        selection_add=[
            ('others', 'Others'),
        ], ondelete={'others': 'cascade'})

    line_type = fields.Selection([
        ('default', 'Default'),
        ('advance_payment', 'Advance Payment'),
        ('retention', 'Retention'),
        ('performance_bond', 'Performance Bond'),
        ('back_charge', 'Back Charge'),
        ('saudization_deduction', 'Saudization Deduction')
        ], default='default', copy=True)

    @api.depends('move_id')
    def _compute_display_type(self):
        for line in self.filtered(lambda l: not l.display_type):
            # avoid cyclic dependencies with _compute_account_id
            account_set = self.env.cache.contains(line, line._fields['account_id'])
            tax_set = self.env.cache.contains(line, line._fields['tax_line_id'])
            if line.move_id.is_invoice():
                if tax_set and line.tax_line_id:
                    line.display_type = 'tax'
                elif account_set and line.account_id.account_type in ['asset_receivable', 'liability_payable']:
                    line.display_type = 'payment_term'
                elif line.line_type != 'product':
                    line.display_type = 'others'
                else:
                    line.display_type = 'product'
            else:
                line.display_type = 'product'
            # line.display_type = (
            #     'tax' if tax_set and line.tax_line_id else
            #     'payment_term' if account_set and line.account_id.account_type in ['asset_receivable', 'liability_payable'] else
            #     'product'
            #     'others': if line.line_type != 'product' else
            # ) if line.move_id.is_invoice() else 'product'

#     @api.returns('self', lambda value: value.id)
#     def copy(self, default=None):
#         print("==self==", self)
#         print("==default==", default)
#         jlkjlj
#         # default = dict(default or {})
#         # if default.get('code', False):
#         #     return super(AccountAccount, self).copy(default)
#         # try:
#         #     default['code'] = (str(int(self.code) + 10) or '').zfill(len(self.code))
#         #     default.setdefault('name', _("%s (copy)") % (self.name or ''))
#         #     while self.env['account.account'].search([('code', '=', default['code']),
#         #                                               ('company_id', '=', default.get('company_id', False) or self.company_id.id)], limit=1):
#         #         default['code'] = (str(int(default['code']) + 10) or '')
#         #         default['name'] = _("%s (copy)") % (self.name or '')
#         # except ValueError:
#         #     default['code'] = _("%s (copy)") % (self.code or '')
#         #     default['name'] = self.name
#         return super(AccountMoveLine, self).copy(default)

class ResPartner(models.Model):
    _inherit = 'res.partner'

    building_no = fields.Char('Building No')
    additional_no = fields.Char('Additional No')
    other_seller_id = fields.Char('Other Seller Id')
    # is_subcontractor = fields.Boolean('Is Subcontractor?')
    back_charge_account_id = fields.Many2one('account.account', 'Back Charge Account')
    sau_deduction_account_id = fields.Many2one('account.account', 'Saudization Deduction Account')
    arabic_name = fields.Char('Arabic Name')
    cr_number = fields.Char('CR Number')


class ResCompany(models.Model):
    _inherit = 'res.company'

    report_header_logo = fields.Binary('Header')
    report_footer_logo = fields.Binary('Footer')
    building_no = fields.Char(related='partner_id.building_no', store=True, readonly=False, string='Building No')
    additional_no = fields.Char(related='partner_id.additional_no', store=True, readonly=False, string='Additional No')
    other_seller_id = fields.Char(related='partner_id.other_seller_id', store=True, readonly=True, string='Other Seller Id')
    arabic_name = fields.Char('Name')
    arabic_street = fields.Char('Street ')
    arabic_street2 = fields.Char('Street2 ')
    arabic_city = fields.Char('City ')
    arabic_state = fields.Char('State ')
    arabic_country = fields.Char('Country ')
    arabic_zip = fields.Char('Zip ')
    


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def get_product_arabic_name(self,pid):
        # translation = self.env['ir.translation'].search([
        #     ('name','=','product.product,name'),('state','=','translated'),
        #     ('res_id','=',pid)])
        # if translation :
        #     return translation.value
        # else: 
        #     product = self.env['product.product'].browse(int(pid))
        #     translation = self.env['ir.translation'].search([
        #         ('name','=','product.product,name'),('state','=','translated'),
        #         ('res_id','=',product.product_tmpl_id.id)])
        #     if translation :
        #         return translation.value
        return _(pid.display_name)   

    @api.model
    def get_qr_code(self):

        def get_qr_encoding(tag, field):
            company_name_byte_array = field.encode('UTF-8')
            company_name_tag_encoding = tag.to_bytes(length=1, byteorder='big')
            company_name_length_encoding = len(company_name_byte_array).to_bytes(length=1, byteorder='big')
            return company_name_tag_encoding + company_name_length_encoding + company_name_byte_array

        qr_code_str = ''
        seller_name_enc = get_qr_encoding(1, self.company_id.display_name)
        company_vat_enc = get_qr_encoding(2, self.company_id.vat or '')
        time_sa = fields.Datetime.context_timestamp(self.with_context(tz='Asia/Riyadh'), self.date_order or self.create_date)
        timestamp_enc = get_qr_encoding(3, time_sa.isoformat())
        invoice_total_enc = get_qr_encoding(4, str(self.amount_total))
        total_vat_enc = get_qr_encoding(5, str(self.currency_id.round(self.amount_total - self.amount_untaxed)))

        str_to_encode = seller_name_enc + company_vat_enc + timestamp_enc + invoice_total_enc + total_vat_enc
        qr_code_str = base64.b64encode(str_to_encode).decode('UTF-8')
        print("==qr_code_str==", qr_code_str)
        return qr_code_str

    def amount_word(self, amount):
        language = self.partner_id.lang or 'en'
        language_id = self.env['res.lang'].search([('code', '=', 'ar_001')])
        if language_id:
            language = language_id.iso_code
        amount_str =  str('{:2f}'.format(amount))
        amount_str_splt = amount_str.split('.')
        before_point_value = amount_str_splt[0]
        after_point_value = amount_str_splt[1][:2]           
        before_amount_words = num2words(int(before_point_value),lang=language)
        after_amount_words = num2words(int(after_point_value),lang=language)
        amount = before_amount_words + ' ' + after_amount_words
        return amount

    def amount_total_words(self, amount):
        words_amount = self.company_id.currency_id.amount_to_text(amount)
        return words_amount


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    def get_product_arabic_name(self,pid):
        # translation = self.env['ir.translation'].search([
        #     ('name','=','product.product,name'),('state','=','translated'),
        #     ('res_id','=',pid)])
        # if translation :
        #     return translation.value
        # else: 
        #     product = self.env['product.product'].browse(int(pid))
        #     translation = self.env['ir.translation'].search([
        #         ('name','=','product.product,name'),('state','=','translated'),
        #         ('res_id','=',product.product_tmpl_id.id)])
        #     if translation :
        #         return translation.value
        return _(pid.display_name) 

    @api.model
    def get_qr_code(self):

        def get_qr_encoding(tag, field):
            company_name_byte_array = field.encode('UTF-8')
            company_name_tag_encoding = tag.to_bytes(length=1, byteorder='big')
            company_name_length_encoding = len(company_name_byte_array).to_bytes(length=1, byteorder='big')
            return company_name_tag_encoding + company_name_length_encoding + company_name_byte_array

        qr_code_str = ''
        seller_name_enc = get_qr_encoding(1, self.company_id.display_name)
        company_vat_enc = get_qr_encoding(2, self.company_id.vat or '')
        time_sa = fields.Datetime.context_timestamp(self.with_context(tz='Asia/Riyadh'), self.date_order or self.create_date)
        timestamp_enc = get_qr_encoding(3, time_sa.isoformat())
        invoice_total_enc = get_qr_encoding(4, str(self.amount_total))
        total_vat_enc = get_qr_encoding(5, str(self.currency_id.round(self.amount_total - self.amount_untaxed)))

        str_to_encode = seller_name_enc + company_vat_enc + timestamp_enc + invoice_total_enc + total_vat_enc
        qr_code_str = base64.b64encode(str_to_encode).decode('UTF-8')
        return qr_code_str

    def amount_word(self, amount):
        language = self.partner_id.lang or 'en'
        language_id = self.env['res.lang'].search([('code', '=', 'ar_001')])
        if language_id:
            language = language_id.iso_code
        amount_str =  str('{:2f}'.format(amount))
        amount_str_splt = amount_str.split('.')
        before_point_value = amount_str_splt[0]
        after_point_value = amount_str_splt[1][:2]           
        before_amount_words = num2words(int(before_point_value),lang=language)
        after_amount_words = num2words(int(after_point_value),lang=language)
        amount = before_amount_words + ' ' + after_amount_words
        return amount

    def amount_total_words(self, amount):
        words_amount = self.company_id.currency_id.amount_to_text(amount)
        return words_amount


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    def reverse_moves(self):
        res = super(AccountMoveReversal, self).reverse_moves()
        if res.get('res_model') == 'account.move':
            account_move_id = self.env['account.move'].search([('id', '=', res.get('res_id'))])
            if account_move_id:
                account_move_id._compute_cal_move_fields()
                account_move_id.onchange_advance_payment()
        return res
