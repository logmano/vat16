from odoo import _, api, fields, models, tools


class ResPartnerInherit(models.AbstractModel):

    _inherit = "res.partner"

    company_id = fields.Many2one(
        "res.company", "Company", index=True, default=lambda self: self.env.company
    )

    @api.model
    def default_get(self, fields_list):
        res = super(ResPartnerInherit, self).default_get(fields_list)
        company = self.env.company
        if company:
            res["company_id"] = company.id
        return res
