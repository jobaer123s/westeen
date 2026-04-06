{
    "name": "Bulk Manufacturing Orders",
    "summary": "Create multiple manufacturing orders for various size variants from a single page.",
    "description": """Provides the base data model and views for orchestrating bulk MO creation from one screen.
    The actual business logic is documented in doc/ARCHITECTURE.md and tracked in models/bulk_mo.py.""",
    "version": "18.0.1.0.0",
    "author": "Westeen",
    "website": "",
    "license": "LGPL-3",
    "category": "Manufacturing/Manufacturing",
    "depends": [
        "mrp",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/bulk_mo_views.xml",
    ],
    "installable": True,
}
