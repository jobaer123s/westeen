"""Data model + orchestration methods for bulk manufacturing orders.

This module intentionally keeps its business logic thin while documenting the
architecture that will eventually power the UI defined in doc/ARCHITECTURE.md.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class MrpBulkOrder(models.Model):
    """Container record representing a batch of size-specific manufacturing orders."""

    _name = "mrp.bulk.order"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Bulk Manufacturing Order"
    name = fields.Char(
        string="Reference",
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _("New"),
    )
    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Product Template",
        required=True,
        tracking=True,
    )
    bom_id = fields.Many2one(
        "mrp.bom",
        string="Bill of Materials",
        help="Optional override for the BOM applied to every generated MO.",
    )
    scheduled_date = fields.Datetime(
        string="Date",
        default=fields.Datetime.now,
        tracking=True,
    )
    line_ids = fields.One2many(
        "mrp.bulk.order.line",
        "bulk_order_id",
        string="Variant Lines",
        copy=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("partial", "Partially Produced"),
            ("done", "Produced All"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        tracking=True,
    )
    mo_strategy = fields.Selection(
        selection=[
            ("split", "Separate MO per line"),
            ("single", "Single MO for entire batch"),
        ],
        string="MO Strategy",
        default="split",
        help="If set to single, all size variants share one MO via aggregate demand.",
    )
    is_done = fields.Boolean(
        string="All Lines Done",
        compute="_compute_is_done",
        store=True,
    )

    def _ensure_sequence(self):
        seq = self.env.ref("custom_mo.seq_mrp_bulk_order", raise_if_not_found=False)
        if not seq:
            return
        for order in self.filtered(lambda o: o.name == _("New")):
            order.name = seq.next_by_id()
        self._refresh_display_name()

    def write(self, vals):
        res = super().write(vals)
        if not self._context.get("bulk_mo_skip_name_refresh") and (
            "product_tmpl_id" in vals or "name" in vals
        ):
            self._refresh_display_name()
        return res

    def _refresh_display_name(self):
        for order in self:
            if not order.name or order.name == _("New"):
                continue
            base_name = order.name.split(" (")[0]
            display = base_name
            if order.product_tmpl_id:
                display = f"{base_name} ({order.product_tmpl_id.display_name})"
            if order.name != display:
                order.with_context(bulk_mo_skip_name_refresh=True).write({"name": display})

    def action_create_orders(self):
        """Create/refresh mrp.production records for every line."""
        for order in self:
            order._ensure_sequence()
            if not order.line_ids:
                raise UserError(_("Add at least one variant line."))
            if order.mo_strategy == "single":
                order._create_single_mo()
            else:
                order._create_split_mos()
        return True

    def action_confirm(self):
        """Confirm the bulk order and ensure related MOs exist."""
        for order in self:
            order.action_create_orders()
            timestamp = fields.Datetime.context_timestamp(order, fields.Datetime.now())
            order.message_post(
                body=_("Bulk MO confirmed on %s") % timestamp.strftime("%Y-%m-%d %H:%M:%S")
            )
            order.state = "confirmed"
            order._sync_state_from_lines()
        return True

    def _create_split_mos(self):
        Production = self.env["mrp.production"]
        for line in self.line_ids:
            if line.production_id:
                continue
            bom = line._get_line_bom()
            values = {
                "product_id": line.product_id.id,
                "product_qty": line.product_qty,
                "qty_producing": line.qty_producing or line.product_qty,
                "product_uom_id": line.product_id.uom_id.id,
                "bom_id": bom.id if bom else False,
                "date_start": self.scheduled_date,
            }
            mo = Production.create(values)
            line.production_id = mo
            mo.action_confirm()

    def _create_single_mo(self):
        Production = self.env["mrp.production"]
        # combine quantities by variant but still note the individual lines
        qty = sum(line.product_qty for line in self.line_ids)
        template_product = self.product_tmpl_id.product_variant_id
        if not template_product:
            raise UserError(_("Configure at least one variant on the template."))
        bom = self.bom_id or template_product.bom_id
        values = {
            "product_id": template_product.id,
            "product_qty": qty,
            "qty_producing": qty,
            "product_uom_id": template_product.uom_id.id,
            "bom_id": bom.id if bom else False,
            "date_start": self.scheduled_date,
            "origin": self.name,
        }
        mo = Production.create(values)
        mo.action_confirm()
        self.line_ids.write({"production_id": mo.id})

    def action_produce_all(self):
        for order in self:
            for line in order.line_ids:
                if line.state in ("done", "cancel"):
                    continue
                order.action_produce_line(line)
            order._sync_state_from_lines()
        return True

    def action_produce_line(self, line):
        self.ensure_one()
        if line.bulk_order_id != self:
            raise UserError(_("Line does not belong to this bulk order."))
        if not line.production_id:
            raise UserError(_("Generate the manufacturing order first."))
        if line.state == "cancel":
            raise UserError(_("This manufacturing order has been cancelled."))
        if not line.qty_producing:
            line.qty_producing = line.product_qty
        qty_to_produce = line.qty_producing or line.product_qty
        if qty_to_produce <= 0:
            raise UserError(_("Quantity to produce must be greater than zero."))
        if qty_to_produce > line.product_qty:
            raise UserError(_("You cannot produce more than the requested quantity."))

        production = line.production_id
        original_qty = production.product_qty
        new_backorders = self.env["mrp.production"]
        if qty_to_produce < original_qty:
            split_result = production._split_productions(
                amounts={production: [qty_to_produce, original_qty - qty_to_produce]},
                cancel_remaining_qty=False,
            )
            production = split_result & production or production
            new_backorders = split_result - production

        production.qty_producing = qty_to_produce
        ctx = {
            "skip_backorder": True,
            "skip_consumption": True,
            "skip_analytic_posting": True,
            "skip_redirection": True,
        }
        res = production.with_context(**ctx).button_mark_done()
        for new_mo in new_backorders:
            self._add_backorder_line(line, new_mo)
        self._sync_state_from_lines()
        return res

    def action_cancel(self):
        for order in self:
            order.state = "cancel"
        return True

    def _add_backorder_line(self, source_line, backorder_mo):
        self.ensure_one()
        self.env["mrp.bulk.order.line"].create(
            {
                "bulk_order_id": self.id,
                "product_id": backorder_mo.product_id.id,
                "product_qty": backorder_mo.product_qty,
                "qty_producing": backorder_mo.product_qty,
                "production_id": backorder_mo.id,
                "bom_id": backorder_mo.bom_id.id
                or (source_line.bom_id.id if source_line.bom_id else False),
            }
        )

    def _sync_state_from_lines(self):
        for order in self:
            if order.state == "cancel":
                continue
            if not order.line_ids:
                order.state = "draft"
                continue
            done_count = len(order.line_ids.filtered(lambda l: l.state == "done"))
            if done_count == 0:
                order.state = "confirmed"
            elif done_count == len(order.line_ids):
                order.state = "done"
            else:
                order.state = "partial"

    @api.depends("line_ids.state")
    def _compute_is_done(self):
        for order in self:
            states = order.line_ids.mapped("state")
            order.is_done = bool(states) and all(state in ("done", "cancel") for state in states)

    @api.onchange("product_tmpl_id", "bom_id")
    def _onchange_prefill_lines(self):
        for order in self:
            order._prefill_lines_from_template()

    def _prefill_lines_from_template(self):
        self.ensure_one()
        template = self.product_tmpl_id
        if not template:
            self.line_ids = [(5, 0, 0)]
            return
        variants = self._get_variants_for_bulk_lines()
        if not variants:
            return
        existing_variant_ids = set(self.line_ids.mapped("product_id").ids)
        if existing_variant_ids == set(variants.ids):
            return
        commands = [(5, 0, 0)]
        Bom = self.env["mrp.bom"]
        bom_map = Bom._bom_find(variants)
        for variant in variants:
            bom = self.bom_id or bom_map.get(variant)
            commands.append(
                (
                    0,
                    0,
                    {
                        "product_id": variant.id,
                        "bom_id": bom.id if bom else False,
                        "product_qty": 1.0,
                        "qty_producing": 0.0,
                    },
                )
            )
        self.line_ids = commands

    def _get_variants_for_bulk_lines(self):
        template = self.product_tmpl_id
        if not template:
            return self.env["product.product"]
        if self.bom_id:
            implied = self.bom_id.product_id or self.bom_id.product_tmpl_id.product_variant_ids
            if implied:
                return implied
        variant_boms = template.bom_ids.filtered("product_id")
        if variant_boms:
            return variant_boms.mapped("product_id")
        return template.product_variant_ids


class MrpBulkOrderLine(models.Model):
    """Represents one size/variant row in the bulk MO grid."""

    _name = "mrp.bulk.order.line"
    _description = "Bulk Manufacturing Order Line"

    bulk_order_id = fields.Many2one(
        "mrp.bulk.order",
        string="Bulk Order",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Variant",
        required=True,
    )
    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Product Template",
        related="product_id.product_tmpl_id",
        store=True,
        readonly=True,
    )
    variant_name = fields.Char(
        string="Product Variants",
        compute="_compute_variant_name",
        store=True,
    )
    bom_id = fields.Many2one(
        "mrp.bom",
        string="Bill of Materials",
        help="Optional override BOM for this line only.",
    )
    product_qty = fields.Float(string="Requested Qty", required=True, default=1.0)
    qty_producing = fields.Float(
        string="Qty Produce",
        default=0.0,
        help="Editable quantity passed to the MO when finishing.",
        copy=False,
    )
    production_id = fields.Many2one(
        "mrp.production",
        string="Manufacturing Order",
        readonly=True,
        copy=False,
    )
    state = fields.Selection(
        related="production_id.state",
        string="MO State",
        store=True,
        readonly=True,
    )

    def _get_line_bom(self):
        return self.bom_id or self.bulk_order_id.bom_id or self.product_id.bom_id

    def action_produce_now(self):
        for line in self:
            line.bulk_order_id.action_produce_line(line)
        return True

    def action_cancel_line(self):
        for line in self:
            if not line.production_id:
                continue
            if line.production_id.state == "done":
                raise UserError(_("You cannot cancel a completed manufacturing order."))
            line.production_id.action_cancel()
            line.bulk_order_id._sync_state_from_lines()
        return True

    @api.depends("product_id")
    def _compute_variant_name(self):
        for line in self:
            line.variant_name = line.product_id.display_name or ""
