# -*- coding: utf-8 -*-
from odoo import api, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _process_pos_ui_product_product(self, products, config):
        super()._process_pos_ui_product_product(products, config)
        if not config:
            return
        location = config.pos_source_location_id
        if not location:
            return
        product_ids = [product['id'] for product in products if product.get('id')]
        stock_map = self.get_stock_by_location(product_ids, location.id)
        for product in products:
            product_id = product.get('id')
            if not product_id:
                continue
            if product_id in stock_map:
                product['qty_available'] = stock_map[product_id]
                product['pos_location_qty_available'] = stock_map[product_id]
                product['pos_location_id'] = location.id

    @api.model
    def get_stock_by_location(self, product_ids, location_id):
        if not product_ids or not location_id:
            return {}
        location = self.env['stock.location'].sudo().browse(location_id)
        if not location:
            return {}
        company = location.company_id or self.env.company
        products = self.sudo().with_company(company).browse(product_ids)
        Quant = self.env['stock.quant'].sudo().with_company(company)
        stock_map = {}
        for product in products:
            stock_map[product.id] = Quant._get_available_quantity(product, location)
        return stock_map
