# -*- coding: utf-8 -*-
from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    pos_source_location_id = fields.Many2one(
        'stock.location',
        string='POS Source Location',
        related='picking_type_id.default_location_src_id',
        store=True,
        readonly=True,
    )
