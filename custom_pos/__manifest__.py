# -*- coding: utf-8 -*-
{
    'name': 'Westeen Custom POS',
    'version': '18.0.1.0.0',
    'summary': 'Show location specific stock levels inside the POS product info popup.',
    'depends': ['point_of_sale', 'stock'],
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'custom_pos/static/src/app/screens/product_screen/product_info_popup/product_info_popup.js',
        ],
    },
    'license': 'LGPL-3',
}
