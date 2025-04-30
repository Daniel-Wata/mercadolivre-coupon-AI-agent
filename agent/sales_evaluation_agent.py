from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from typing import Dict, Any
import os
from langchain_core.runnables.graph import CurveStyle, MermaidDrawMethod, NodeStyles

# Import all node functions from the new file
from agent.workflow_nodes import (
    is_it_a_mercadolivre_sale,
    coupon_or_direct_compare,
    coupon_extraction,
    filter_viewed_coupons,
    get_wishlist_items,
    optimise_cart,
    craft_deal_message,
    insert_coupons_in_database,
    continue_or_end,
    route_after_filter,
    identity,
    State,
    direct_compare_deal_message
)

# Initialize the LLM for any local usage
llm = ChatGroq(
    model_name="llama-3.3-70b-versatile",
    temperature=0.3
)

# Database connection parameters
DB_USER = os.getenv("DATABASE_USER", "postgres")
DB_PASSWORD = os.getenv("DATABASE_PASSWORD", "postgres")
DB_NAME = os.getenv("DATABASE_NAME", "telegram_bot")
DB_HOST = os.getenv("DATABASE_HOST", "localhost")
DB_PORT = os.getenv("DATABASE_PORT", "5432")

# Create connection string
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def instantiate_workflow():
    workflow = StateGraph(State)

    workflow.add_node("get_wishlist_items", get_wishlist_items)
    workflow.add_node("is_mercadolivre_sale", is_it_a_mercadolivre_sale)
    workflow.add_node("coupon_extraction", coupon_extraction)
    workflow.add_node("filter_viewed_coupons", filter_viewed_coupons)
    workflow.add_node("optimise_cart", optimise_cart)
    workflow.add_node("craft_deal_message", craft_deal_message)
    workflow.add_node("insert_coupons_in_database", insert_coupons_in_database)
    workflow.add_node("coupon_or_direct_compare", coupon_or_direct_compare)
    workflow.add_node("direct_compare_deal_message", direct_compare_deal_message)

    workflow.add_edge(START, "get_wishlist_items")
    workflow.add_conditional_edges("get_wishlist_items", continue_or_end, {"continue": "is_mercadolivre_sale", "end": END})
    workflow.add_conditional_edges("is_mercadolivre_sale", coupon_or_direct_compare, {"coupon": "coupon_extraction", "direct_compare": "direct_compare_deal_message", "end": END})
    workflow.add_edge("coupon_extraction", "filter_viewed_coupons")
    workflow.add_conditional_edges(
        "filter_viewed_coupons",
        route_after_filter,
        {"work": "parallel_router", "end": END},
    )

    workflow.add_node("parallel_router", identity)

    # unconditional edges from the router to both workers
    workflow.add_edge("parallel_router", "insert_coupons_in_database")
    workflow.add_edge("parallel_router", "optimise_cart")

    workflow.add_edge("optimise_cart", "craft_deal_message")
    workflow.add_edge("craft_deal_message", END)
    workflow.add_edge("direct_compare_deal_message", END)


    app = workflow.compile()
    #try:
    #    with open("workflow_graph.png", "wb") as f:
    #        f.write(app.get_graph().draw_mermaid_png(
    #        curve_style=CurveStyle.LINEAR,
    #        node_colors=NodeStyles(first="#ffdfba", last="#baffc9", default="#fad7de"),
    #        wrap_label_n_words=9,
    #        output_file_path=None,
    #        draw_method=MermaidDrawMethod.PYPPETEER,
    #        background_color="white",
    #        padding=10,
    #    ))
    #except Exception as e:
    #    app.get_graph().print_ascii()
    #    print("Unable to save the graph image:",e)
    return app

def run_workflow(message: str) -> Dict[str, Any]:
    workflow = instantiate_workflow()
    initial_state = {"message": message}
    data = workflow.invoke(initial_state)
    return data

if __name__ == "__main__":
    run_workflow("test")
