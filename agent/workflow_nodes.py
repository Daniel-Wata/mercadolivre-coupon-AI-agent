from langchain_groq import ChatGroq
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
import re
import json
from typing import Literal, List, Dict, Any, TypedDict
from decimal import Decimal
import psycopg2
from itertools import permutations, chain, combinations
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get database URL from environment variables
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost/telegram_data")

# Initialize the LLM
llm = ChatGroq(
    model_name="llama-3.3-70b-versatile",
    temperature=0.3
)

# Type definitions
class Coupon(TypedDict):
    code: str
    discount_value: float
    discount_percentage: float
    max_discount: float
    minimun_purchase: float
    product_type_limit: str
    discount_type: str

class WishlistItem(TypedDict):
    url: str
    title: str
    price: float

class State(TypedDict):
    message: str
    coupons: List[Coupon]
    wishlist: List[WishlistItem]
    should_continue: bool
    best_plan: Dict[str, Any]
    deal_message: str
    direct_compare: bool

class directCompareState(TypedDict):
    message: str
    wishlist: List[WishlistItem]
    should_continue: bool
    deal_message: str

def test_urls(message: str) -> bool:
    """
    Looks for urls in the text and calls them, determining the follow up urls and returning them.
    """
    import re
    import requests
    
    # Updated regex pattern to better match URLs
    urls = re.findall(r'https?://[^\s]+', message)
    return_urls = []
    for url in urls:
        print(f"Checking URL: {url}")
        try:
            response = requests.get(url, timeout=5, allow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'})
            if response.status_code == 200:
                # Get the final URL after redirects
                final_url = response.url
                print(f"Original URL: {url}")
                print(f"Final URL after redirects: {final_url}")
                return_urls.append(final_url)
        except Exception as e:
            print(f"Error calling URL: {url}")
            print(e)
    return return_urls

def coupon_or_direct_compare(state) -> Literal["coupon", "direct_compare", "end"]:
    """
    Return "continue" if we should keep going,
    or "end" to stop the run immediately.
    """
    if state['should_continue'] == False:
        print("Decided to end")
        return "end"
    elif state['direct_compare']:
        print("Decided to direct compare")
        return "direct_compare"
    else:
        print("Decided to go with coupon workflow")
        return "coupon"

def decimal_to_float(obj):
    """Convert Decimal objects to float for JSON serialization"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(item) for item in obj]
    return obj

def direct_compare_deal_message(state):
    """
    Verifies if the message has a sale for a product in the wishlist
    """
    print("Checking if the message has a sale for a product in the wishlist")
    message = state['message']
    
    # Convert any Decimal objects to float for JSON serialization
    wishlist_for_json = decimal_to_float(state['wishlist'])

    wishlist_text = ""
    for item in wishlist_for_json:
        wishlist_text += f"- {item['title']} - R$ {item['price']}\n"
    
    llm_prompt = f"""
    You are sales validator that validates if the sale sent by the user is similar to the products in the wishlist.
    You will be given a message from a sales group and a wishlist from the user. Your job is to determine if there is a sale for a similar product in the wishlist.
    If there is a sale for a similar product, you will need to return the sale information and the product in the cart it is similar to.
    **Important**: If there are no EXTREMELY similar products, return "no match"

    Similarity is defined by:
    - The sale product has very similar name, or it is the same item, but differ in small details like brand, color, size.
    
    The sale information should include:
    - The product name and sale url fromatted as [product name](sale url)
    - The sale price
    - How to activate the sale

    The product in the cart it is similar to should include:
    - The product name and price from the wishlist

    The message should be formatted in Markdown. with proper line breaks and lists.
    REMEMBER: If there is no match, return "no match"

    Example when there is no match:
        **no match**

    Example when there is a match:
        **Promocao de produto similar a sua lista:**
        • [product name](sale url) - R$ 100,00

        **Como ativar a promocao:**
        • Utilize o cupom: `VALE20` no site

        **Essa promocao e simliar ao produto:**
        ID: Product name from wishlist - R$ 100,00

        Short message on what are the similarities and differences between the product in the sale and the product in the wishlist

    wishlist: 
    {wishlist_text}
    """

    message = f"""
    Message: {message}
    """

    response = llm.invoke([SystemMessage(content=llm_prompt), HumanMessage(content=message)])
    print(response.content)
    state['deal_message'] = response.content
    return state


def is_it_a_mercadolivre_sale(state):
    """
    Verifica se a mensagem é uma propaganda de venda de produtos no Mercado Livre:

    Deve buscar links na mensagem e verificar se eles redirecioname para o mercado livre.
    """
    print("Checking if it's a Mercado Livre sale")

    if "mercadolivre" in state['message'].lower() or "mercado livre" in state['message'].lower():
        print("Found Mercado Livre in message")
        state['should_continue'] = True
        return state
    
    urls = test_urls(state['message'])
    for url in urls:
        if "mercadolivre" in url.lower() or "mercado livre" in url.lower():
            print("Found Mercado Livre in URL")
            state['direct_compare'] = False
            return state
    print("No Mercado Livre found")
    state['direct_compare'] = True
    return state

def coupon_extraction_from_message(message: str):
    """
    Uses an LLM to determine if there is a coupon in the message or not and returns a list of coupons codes found
    """

    system_message = """ You are an expert in coupon lookup.
    You will be given a message and you will need to determine if there is a coupon in the message or not.
    If there is a coupon, you will need to return a list of coupon codes and their information.
    If there is no coupon, or there are not enough information on the coupon, you will need to return an empty list.

    You will also look for the coupon informations like:
        - discount_value: the value of the discount
        - discount_percentage: the percentage of the discount
        - max_discount: the maximum discount value if it's a percentage discount
        - discount_type: the type of discount (percentage, value, unknown)
        - minimun_purchase: the minimum purchase value to use the coupon
        - product_type_limit: the product type limit to use the coupon, a word or phrase that describes the product type
        - has_rules: a boolean value to indicate if the message has the coupon rules or not
        
    
    
    The coupon should have a value, a percentage and in case of percentage, a max discount (unless stated otherwise) and a minimun purchase value (unless stated otherwise).

    If there is no information on the coupon directly, mark has_rules as false.
    In the cases of non used keys, return null!

    Return only a JSON with the following format:
    [{"code":"code","discount_value":50,"discount_percentage":10,"max_discount":50, "minimun_purchase":100, "product_type_limit":"moda", "discount_type":"percentage", "has_rules":true}]
    or []

    DO NOT RETURN ANYTHING ELSE.
    """

    human_message = f"""
    Mensagem: {message}
    """

    response = llm.invoke([SystemMessage(content=system_message), HumanMessage(content=human_message)])
    print(response.content)

    text = response.content
    # Look for the JSON in the response
    return json.loads(text[text.find('['): text.rfind(']') + 1])

def coupon_extraction(state):
    """
    Extracts coupons from the message
    """
    print("Extracting coupons from message")
    state['coupons'] = coupon_extraction_from_message(state['message'])
    return state

def get_viewed_coupons():
    """
    Get all active coupons from the database
    """
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT code FROM coupons WHERE date_updated > NOW() - INTERVAL '2 day'")
                # return a list of coupon codes
                return [row[0] for row in cur.fetchall()]
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return []

def filter_viewed_coupons(state):
    """
    Check if the coupons are new
    """
    print("Filtering viewed coupons")
    viewed_coupons = get_viewed_coupons()
    state['coupons'] = [coupon for coupon in state['coupons'] if coupon['code'] not in viewed_coupons or coupon['has_rules'] == False]

    if len(state['coupons']) == 0:
        print("No new coupons found")
        state['should_continue'] = False
    else:
        print("New coupons found")
        state['should_continue'] = True

    return state

def get_wishlist_items(state):
    """
    Get the wishlist items from the database
    """
    print("Getting wishlist items")
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT title, price, url FROM wishlist")
                # return a list with a dictionary for each item
                state['wishlist'] = [{"title": row[0], "price": row[1], "url": row[2]} for row in cur.fetchall()]
        
        if len(state['wishlist']) == 0:
            print("No wishlist items found")
            state['should_continue'] = False
        else:
            print("Wishlist items found")
            state['should_continue'] = True
    except Exception as e:
        print(f"Error connecting to database: {e}")
        state['wishlist'] = []
        state['should_continue'] = False
    
    return state

def insert_coupons_in_database(state):
    """ 
    Function that gets the list of coupons and inserts them in the postgres database
    """
    if len(state.get('coupons',[])) == 0:
        print("no new coupons to add")
        return state
    
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                for coupon in [coupon for coupon in state['coupons'] if coupon['has_rules'] == True]:
                    cur.execute("INSERT INTO coupons (code, discount_value, discount_percentage, max_discount, minimun_purchase, product_type_limit, discount_type) VALUES (%s, %s, %s, %s, %s, %s, %s)", 
                               (coupon['code'], coupon['discount_value'], coupon['discount_percentage'], 
                                coupon['max_discount'], coupon['minimun_purchase'], 
                                coupon['product_type_limit'], coupon['discount_type']))
                conn.commit()
    except Exception as e:
        print(f"Error inserting coupons into database: {e}")

def continue_or_end(state) -> Literal["continue", "end"]:
    """
    Return "continue" if we should keep going,
    or "end" to stop the run immediately.
    """
    print(f"Decided to { 'continue' if state.get('should_continue', True) else 'end'}")

    return "continue" if state.get("should_continue", True) else "end"

# ---------- helpers -----------------------------------------------------
def cart_saving(cart_total: Decimal, c: Dict[str, Any]) -> Decimal:
    if cart_total < (c["minimun_purchase"] or 0):
        return Decimal("0")        # coupon can't be applied
    if c["discount_value"] is not None:
        return min(Decimal(c["discount_value"]), cart_total)
    # percentage path
    pct = Decimal(c["discount_percentage"]) / 100
    raw = cart_total * pct
    if c["max_discount"] is not None:
        raw = min(raw, Decimal(c["max_discount"]))
    return raw

def all_partitions(items: List[int]):
    """Return every partition of item indices (bruteforce, n ≤ 10)."""
    if not items:
        return [[]]
    first, rest = items[0], items[1:]
    for part in all_partitions(rest):
        for i in range(len(part)):
            yield part[:i] + [[first] + part[i]] + part[i+1:]
        yield [[first]] + part

def greedy_partitions(indices, prices, coupons):
    """Yield one reasonable partition quickly (big datasets)."""
    remaining = set(indices)
    for c in coupons:
        if not remaining:
            break
        trigger = (
            (Decimal(c["max_discount"]) / (Decimal(c["discount_percentage"])/100))
            if c["discount_percentage"] and c["max_discount"]
            else 0
        )
        current, total = [], Decimal("0")
        for i in sorted(remaining, key=lambda x: prices[x], reverse=True):
            if total < trigger:
                current.append(i); total += prices[i]
        remaining -= set(current)
        yield current
    if remaining:
        yield list(remaining)

def optimise_cart(state):
    coupons:   List[Dict[str, Any]] = state.get("coupons", [])
    wishlist:  List[Dict[str, Any]] = state.get("wishlist", [])

    filtered_coupons = [coupon for coupon in coupons if coupon['has_rules'] == True]
    # 0) guard-rails ------------------------------------------------
    if not filtered_coupons or not wishlist:
        state["best_plan"] = {"total_saving": 0.0, "carts": []}
        return state                        # ← must return!

    # 1) helper to compute saving for one cart/coupon --------------
    def saving(subtotal: Decimal, c: Dict[str, Any]) -> Decimal:
        mp = Decimal(str(c.get("minimun_purchase") or 0))
        if subtotal < mp:
            return Decimal("0")
        if c["discount_value"] is not None:
            return min(Decimal(c["discount_value"]), subtotal)
        pct = Decimal(c["discount_percentage"]) / 100
        raw = subtotal * pct
        if c["max_discount"] is not None:
            raw = min(raw, Decimal(c["max_discount"]))
        return raw

    # 2) Try all possible item combinations with each coupon
    prices = [Decimal(str(it["price"])) for it in wishlist]
    idxs = list(range(len(prices)))
    
    # Track best configuration for maximum percentage discount
    best_percentage = Decimal("0")
    best_absolute_saving = Decimal("0")
    best_carts = []
    
    # For each coupon, try all possible item combinations
    for coupon in filtered_coupons:
        min_purchase = Decimal(str(coupon.get("minimun_purchase") or 0))
        
        # Try all possible subsets of items (from 1 item to all items)
        for size in range(1, len(idxs) + 1):
            for combo in combinations(idxs, size):
                subtotal = sum(prices[i] for i in combo)
                
                # Skip if below minimum purchase
                if subtotal < min_purchase:
                    continue
                
                save = saving(subtotal, coupon)
                save_percentage = (save / subtotal * 100) if subtotal > 0 else Decimal("0")
                
                # If this gives a better percentage discount, update our best plan
                if save_percentage > best_percentage:
                    best_percentage = save_percentage
                    best_absolute_saving = save
                    
                    cart = {
                        "coupon": coupon["code"],
                        "items": [wishlist[i] for i in combo],
                        "subtotal": float(subtotal),
                        "saving": float(save),
                        "saving_percentage": float(save_percentage)
                    }
                    
                    best_carts = [cart]  # Just keep the single best cart
                
                # If percentage is the same, use absolute discount as tiebreaker
                elif save_percentage == best_percentage and save > best_absolute_saving:
                    best_absolute_saving = save
                    
                    cart = {
                        "coupon": coupon["code"],
                        "items": [wishlist[i] for i in combo],
                        "subtotal": float(subtotal),
                        "saving": float(save),
                        "saving_percentage": float(save_percentage)
                    }
                    
                    best_carts = [cart]  # Just keep the single best cart
    
    state["best_plan"] = {
        "total_saving": float(sum(Decimal(str(cart["saving"])) for cart in best_carts)),
        "max_percentage": float(best_percentage),
        "carts": best_carts,
    }
    return state

def identity(state):
    return state

def craft_deal_message(state):
    """Produce an LLM-written, friendly explanation of the best plan."""
    system_prompt = """
   You are a shopping assistant.  Write short, upbeat messages
    in Brazilian Portuguese.
    The goal: help the user apply new Mercado Livre coupons
    to the products in their wish-list, maximising total savings, by sending him a message in TELEGRAM.

    • List only the coupons (state["coupons"]) and explain, in one line
      each, the essential rule (e.g. "20 % off até R$ 50, compra mínima R$ 49"). 
      **Important** If the coupon has no rules (has_rules is false or there is no information on the coupon), express that in the message, that no rules were found in the message fot that coupon, that if another future message explains it, we will re-send it.
    • Then describe the recommended cart split from state["best_plan"], if not present, ignore this section:
         – for each cart, say: 
          - which coupon to use,
          - which items go inside (name and url), 
          - the subtotal
          - how much the coupon knocks off (Value and percentage).
    • Finish with the grand total the user saves, if state["best_plan"] is not present, ignore this section.
    • Divide the message into 2 parts, using bullet points:
        - List only the *new* coupons (state["coupons"]) and explain, in one line
          each, the code in `code` andthe essential rule (e.g. "20 % off até R$ 50, compra mínima R$ 49").
        - Then describe the recommended cart split from state["best_plan"], dividing the items into carts and explaining which coupon to use for each cart, with the total savings and percentual savings.
    • Always skip 2 lines between each part of the message.

    Suggested format:

**Cupons disponíveis:**
• `MODABBB50`: 50% de desconto, até R$ 300, compra mínima R$ 30, para produtos selecionados

**Plano de compras recomendado:**
    🛒 **Carrinho 1: **
        - Cupom: `MODABBB50`
        - Itens: 
            - [item exemplo 1](https://www.example.com/painel-ripado)
            - [item exemplo 2](https://www.example.com/filamento-pla)
        - Subtotal: R$ 1330,00
        - Desconto: R$ 300,00

💰Total de economia: R$ 300,00 (22% off)
    """

    # --- 1) deep-copy & cast Decimal → float ---------------------
    def cast(o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, list):
            return [cast(x) for x in o]
        if isinstance(o, dict):
            return {k: cast(v) for k, v in o.items()}
        return o

    payload = {
        "coupons":  state.get("coupons", []),
        "wishlist": cast(state.get("wishlist", [])),
        "plan":     cast(state.get("best_plan", {})),
    }

    print(payload)

    # --- 2) call the LLM ----------------------------------------
    response = llm.invoke([
        SystemMessage(content=system_prompt.strip()),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False))
    ])

    state["deal_message"] = response.content.strip()
    return state

def route_after_filter(state):
    # stop everything?
    if not state.get("should_continue", True):
        return "end"
    return "work" 