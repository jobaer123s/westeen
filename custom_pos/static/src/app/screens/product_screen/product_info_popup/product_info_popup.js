/** @odoo-module */
import { ProductInfoPopup } from "@point_of_sale/app/screens/product_screen/product_info_popup/product_info_popup";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { onWillStart, onWillUpdateProps } from "@odoo/owl";

const superSetup = ProductInfoPopup.prototype.setup;

patch(ProductInfoPopup.prototype, {
    setup() {
        if (superSetup) {
            superSetup.call(this, ...arguments);
        }
        this.orm = useService("orm");
        onWillStart(async () => {
            await this._updatePosLocationInventory(this.props.product);
        });
        onWillUpdateProps(async (nextProps) => {
            if (nextProps.product?.id !== this.props.product?.id) {
                await this._updatePosLocationInventory(nextProps.product);
            }
        });
    },

    async _updatePosLocationInventory(product) {
        const locationRecord = this.pos?.config?.pos_source_location_id;
        if (!locationRecord || !product || !this.props?.info?.productInfo) {
            return;
        }
        const locationId = locationRecord.id;
        if (!locationId) {
            return;
        }
        try {
            const result = await this.orm.call(
                "product.product",
                "get_stock_by_location",
                [[product.id], locationId]
            );
            if (!result) {
                return;
            }
            const qty = Object.prototype.hasOwnProperty.call(result, product.id)
                ? result[product.id]
                : 0;
            const baseWarehouse = this.props.info.productInfo.warehouses?.[0];
            const uom = baseWarehouse?.uom || product.uom_id?.name || "";
            const forecasted = qty;
            const locationName =
                locationRecord.display_name || locationRecord.complete_name || locationRecord.name;
            this.props.info.productInfo.warehouses = [
                {
                    name: locationName,
                    available_quantity: qty,
                    forecasted_quantity: forecasted,
                    uom,
                },
            ];
            this.render(true);
        } catch (error) {
            console.error("Failed to fetch POS location stock", error);
        }
    },
});
