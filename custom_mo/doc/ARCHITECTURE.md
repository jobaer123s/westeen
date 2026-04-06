# Bulk Manufacturing Orders – Architecture

This module implements the blueprint captured in `bulk_mo_architecture_v2.svg`.
The diagram already fixes three pillars (menu, header model, line model) and the
implementation mirrors that layout.

## 1. Menu / action placement
- Hook into `mrp.menu_mrp_manufacturing` with sequence **5** so the entry shows up
  before the native "Manufacturing Orders" list.
- `ir.actions.act_window` serves the combined list/form views for
  `mrp.bulk.order`. List = quick oversight, Form = interactive grid.

## 2. Header model: `mrp.bulk.order`
- Stores shared context: reference, product template, optional BOM override,
  scheduled date, strategy flag (`split` vs `single`).
- State is computed from line states (`draft` > `progress` > `done`).
- `action_create_orders()` delegates to `_create_split_mos()` or
  `_create_single_mo()` matching the requirement to optionally keep all sizes in
  one MO.
- `action_produce_all()` (and its helper `action_produce_line(line)`) walks the
  generated manufacturing orders, sets `qty_producing`, and relies on native
  `button_mark_done()` so we inherit Odoo's backorder flow.

## 3. Line model: `mrp.bulk.order.line`
- One row per size (`product.product`), storing requested qty, editable
  `qty_producing`, and the link to the actual `mrp.production` record.
- `state` is a related field that stays synchronized with the underlying MO. No
  custom state machine is required.
- `_get_line_bom()` provides a single decision point for grabbing the right BOM
  (order-level override -> variant-level fallback).

## 4. Flow
1. Planner opens the **Bulk MO Orders** menu, creates a batch, and enters
   multiple size lines on the same page.
2. Clicking **Generate MOs**:
   - assigns a sequence to the bulk order (optional – add an ir.sequence later),
   - validates each line, and either creates individual `mrp.production` records
     or one consolidated MO depending on `mo_strategy`.
   - confirms the generated MOs so they appear in the standard MRP kanban/list.
3. From the same form, the planner can mark lines (or all lines) done; the code
   updates `qty_producing` and calls the standard `button_mark_done()`, letting
   Odoo handle backorders when quantities differ.

## 5. Extension points
- **Wizards**: an optional wizard can import a CSV of variants and push them into
  `line_ids` before running `action_create_orders()`.
- **Security**: grant create/write access to the same groups that can work on
  manufacturing orders (`mrp.group_mrp_user`).
- **Automations**: scheduled action could auto-close batches once all lines hit
  `done`.

This outline keeps the behavior compatible with core manufacturing processes
while satisfying the requirement of managing multiple size variants on a single
page without forcing separate manufacturing orders in every scenario.
