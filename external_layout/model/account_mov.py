import base64

try:
    import qrcode
except ImportError:
    qrcode = None

from io import BytesIO
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, AccessError


class AccountMove(models.Model):
    _inherit = "account.move"

    # post_date = fields.Datetime('Post Date')
    bill_qr_code_str = fields.Char(string="QR CodeStr", compute="_compute_qr_code_str")

    @api.depends(
        "amount_untaxed",
        "amount_tax",
        "create_date",
        "move_type",
        "company_id",
        "company_id.vat",
    )
    def _compute_qr_code_str(self):
        def get_qr_encoding(tag, field):
            company_name_byte_array = field.encode("UTF-8")
            company_name_tag_encoding = tag.to_bytes(length=1, byteorder="big")
            company_name_length_encoding = len(company_name_byte_array).to_bytes(
                length=1, byteorder="big"
            )
            return (
                company_name_tag_encoding
                + company_name_length_encoding
                + company_name_byte_array
            )

        for record in self:
            record.bill_qr_code_str = False
            qr_code_str_hash = ""
            if record.create_date and record.company_id.vat:
                seller_name_enc_h = get_qr_encoding(1, record.company_id.display_name)
                company_vat_enc_h = get_qr_encoding(2, record.company_id.vat)
                time_sa1 = fields.Datetime.context_timestamp(
                    self.with_context(tz="Asia/Riyadh"), record.create_date
                )
                timestamp_enc_h = get_qr_encoding(3, time_sa1.isoformat())
                tot = ""
                tx = ""
                if record.move_type in ("out_refund", "in_invoice"):
                    tot = "-" + str(record.currency_id.round(record.amount_total))
                    tx = "-" + str(record.currency_id.round(record.amount_tax))
                else:
                    tot = str(record.currency_id.round(record.amount_total))
                    tx = str(record.currency_id.round(record.amount_tax))
                # total1 = record.currency_id.round(record.amount_total)
                invoice_total_enc_h = get_qr_encoding(4, tot)
                total_vat_enc_h = get_qr_encoding(5, tx)
                str_to_encode_h = (
                    seller_name_enc_h
                    + company_vat_enc_h
                    + invoice_total_enc_h
                    + total_vat_enc_h
                    + timestamp_enc_h
                )
                qr_code_str_hash = base64.b64encode(str_to_encode_h).decode("UTF-8")
            record.bill_qr_code_str = qr_code_str_hash
