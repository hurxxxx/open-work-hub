from ai_do_api.core.workspace_app_registry import (
    WorkspaceAppRegistration,
    WorkspaceNavRegistration,
)


MEAL_INVOICE_OCR_WORKSPACE_APP = WorkspaceAppRegistration(
    app_id="meal-invoice-ocr",
    title="식당 명세서 OCR",
    route_base="/meal-invoice-ocr",
    icon_key="receipt-text",
    enabled_by_default=True,
    visible_by_default=True,
    launcher_category=True,
    nav_items=(
        WorkspaceNavRegistration(
            id="meal-invoice-ocr",
            title="식당 명세서 OCR",
            category="Business",
            icon_key="receipt-text",
        ),
    ),
)
