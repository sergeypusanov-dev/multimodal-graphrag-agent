"""
Orchestrator — routes user queries to specialized virtual agents.
Each agent has its own system prompt and filtered MCP tool set.
"""

SPECIALISTS = {
    "analytics": {
        "name": "WB Analytics",
        "description": "Аналитик продаж Wildberries — воронки, поисковые запросы, конверсии, тренды",
        "system_prompt": (
            "You are a Wildberries sales analytics specialist. "
            "Analyze sales funnels, search queries, conversion rates, and trends. "
            "Always provide specific numbers and actionable insights. "
            "Compare periods when possible. Answer in the user's language."
        ),
        "tool_patterns": [
            "wb_sales_funnel", "wb_sales_funnel_history", "wb_grouped_history",
            "wb_search_queries_report", "wb_search_texts_by_product",
            "wb_get_region_sales",
        ],
        "keywords": [
            "продаж", "аналитик", "воронк", "конверси", "поиск", "запрос",
            "статистик", "динамик", "тренд", "регион", "analytics", "sales",
            "funnel", "search", "trend",
        ],
    },
    "pricing": {
        "name": "WB Pricing Manager",
        "description": "Менеджер ценообразования — цены, скидки, карантин, мониторинг",
        "system_prompt": (
            "You are a Wildberries pricing specialist. "
            "Manage prices, discounts, monitor quarantine status. "
            "Suggest optimal pricing strategies. Answer in the user's language."
        ),
        "tool_patterns": [
            "wb_set_prices", "wb_set_size_prices", "wb_get_prices",
            "wb_get_prices_batch", "wb_get_upload_status",
            "wb_get_quarantine", "wb_get_size_prices",
        ],
        "keywords": [
            "цен", "скидк", "карантин", "price", "discount", "стоимост",
            "наценк", "маржа", "margin",
        ],
    },
    "orders": {
        "name": "WB Orders",
        "description": "Заказы и продажи — история заказов, продажи, возвраты, FBS сборка",
        "system_prompt": (
            "You are a Wildberries orders specialist. "
            "Retrieve orders, sales, returns data. Manage FBS assembly orders. "
            "Always use tools to get real data. Answer in the user's language."
        ),
        "tool_patterns": [
            "wb_get_orders", "wb_get_sales", "wb_get_incomes",
            "wb_get_last_order", "wb_get_new_orders", "wb_get_fbs_orders",
            "wb_get_order_statuses", "wb_cancel_order", "wb_get_order_stickers",
            "wb_get_reshipment_orders", "wb_get_returns_report",
        ],
        "keywords": [
            "заказ", "продаж", "order", "sales", "возврат", "return",
            "FBS", "сборк", "стикер", "отмен", "cancel",
        ],
    },
    "warehouse": {
        "name": "WB Warehouse",
        "description": "Склад и поставки — остатки, склады, поставки, хранение, штрафы",
        "system_prompt": (
            "You are a Wildberries warehouse and supply specialist. "
            "Monitor stocks, manage supplies, track storage costs. "
            "Always use tools to get real data. Answer in the user's language."
        ),
        "tool_patterns": [
            "wb_stocks_report_groups", "wb_stocks_report_products",
            "wb_stocks_report_warehouses", "wb_get_warehouse_stocks",
            "wb_create_supply", "wb_get_supplies", "wb_get_supply",
            "wb_add_orders_to_supply", "wb_deliver_supply", "wb_delete_supply",
            "wb_create_warehouse_report", "wb_warehouse_report_status",
            "wb_download_warehouse_report",
            "wb_get_paid_storage", "wb_get_measurement_penalties",
            "wb_get_blocked_products", "wb_get_shadowed_products",
        ],
        "keywords": [
            "склад", "остаток", "поставк", "хранени", "штраф",
            "stock", "warehouse", "supply", "logistics",
            "blocked", "shadow", "storage",
        ],
    },
    "content": {
        "name": "WB Content Manager",
        "description": "Контент-менеджер — карточки товаров, категории, характеристики, теги",
        "system_prompt": (
            "You are a Wildberries product content specialist. "
            "Manage product cards, categories, characteristics, tags. "
            "Optimize listings for better visibility. Answer in the user's language."
        ),
        "tool_patterns": [
            "wb_get_parent_categories", "wb_get_subjects",
            "wb_get_subject_characteristics", "wb_get_cards_list",
            "wb_update_card", "wb_get_tags", "wb_create_tag",
            "wb_set_card_tags", "wb_delete_cards_to_trash",
            "wb_recover_cards", "wb_get_colors", "wb_get_countries",
        ],
        "keywords": [
            "карточк", "товар", "категори", "характеристик", "тег",
            "описани", "контент", "card", "product", "category", "tag",
            "listing", "SEO",
        ],
    },
    "finance": {
        "name": "WB Finance",
        "description": "Финансы — баланс, отчёты о реализации, приёмка, документы",
        "system_prompt": (
            "You are a Wildberries financial analyst. "
            "Track balance, realization reports, acceptance costs, financial documents. "
            "Provide clear financial summaries. Answer in the user's language."
        ),
        "tool_patterns": [
            "wb_get_balance", "wb_get_realization_report",
            "wb_get_documents",
            "wb_create_acceptance_report", "wb_acceptance_report_status",
            "wb_download_acceptance_report",
        ],
        "keywords": [
            "баланс", "финанс", "отчёт", "отчет", "реализаци", "выплат",
            "приёмк", "приемк", "документ", "акт", "balance", "finance",
            "report", "revenue", "payment",
        ],
    },
}


def classify_specialist(query: str) -> str:
    """Determine which specialist should handle the query."""
    query_lower = query.lower()
    scores = {}
    for key, spec in SPECIALISTS.items():
        score = sum(2 for kw in spec["keywords"] if kw in query_lower)
        scores[key] = score

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "general"
    return best


def get_specialist_tools(specialist_key: str, all_mcp_tools: list) -> list:
    """Filter MCP tools for a specific specialist."""
    if specialist_key == "general" or specialist_key not in SPECIALISTS:
        return all_mcp_tools[:15]

    spec = SPECIALISTS[specialist_key]
    patterns = spec["tool_patterns"]
    filtered = [t for t in all_mcp_tools
                if t["function"]["name"] in patterns]
    return filtered if filtered else all_mcp_tools[:10]


def get_specialist_prompt(specialist_key: str) -> str:
    """Get the system prompt for a specialist."""
    if specialist_key in SPECIALISTS:
        return SPECIALISTS[specialist_key]["system_prompt"]
    return ""


def get_specialist_name(specialist_key: str) -> str:
    """Get human-readable specialist name."""
    if specialist_key in SPECIALISTS:
        return SPECIALISTS[specialist_key]["name"]
    return "General Assistant"
