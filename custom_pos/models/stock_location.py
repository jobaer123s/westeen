# -*- coding: utf-8 -*-
from odoo import api, models


class StockLocation(models.Model):
    _name = 'stock.location'
    _inherit = ['stock.location', 'pos.load.mixin']

    @staticmethod
    def _extract_config_location_id(data):
        config_data = data.get('pos.config', {}).get('data', []) if data else []
        if not config_data:
            return False
        location_value = config_data[0].get('pos_source_location_id')
        if isinstance(location_value, (list, tuple)):
            return location_value[0] if location_value else False
        return location_value

    @api.model
    def _load_pos_data_domain(self, data):
        location_id = self._extract_config_location_id(data)
        if not location_id:
            return [('id', '=', False)]
        return [('id', '=', location_id)]

    @api.model
    def _load_pos_data_fields(self, config_id):
        return ['name', 'complete_name']
