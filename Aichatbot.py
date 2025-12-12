#!/usr/bin/env python3
"""
AI-style CLI chatbot for product & sale JSON files.

Usage:
 - Place product.json and sale.json in same folder (examples below).
 - Run: python ai_shop_chatbot.py
"""

import json
import os
import uuid
import difflib
import re
from datetime import datetime

PRODUCT_FILE = "product.json"
SALE_FILE = "sale.json"

# ---------- Utilities ----------
def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def normalize_products(raw):
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return raw
    raise ValueError("product.json must contain an object or an array")

def ensure_sales_list(raw):
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return [raw]
    return []

def create_invoice_number():
    return "INV-" + datetime.now().strftime("%Y%m%d") + "-" + str(uuid.uuid4())[:8].upper()

# ---------- Product search / fuzzy match ----------
def find_product_by_name(products, name, cutoff=0.6):
    name = (name or "").strip()
    if not name:
        return None

    # exact match first
    for p in products:
        if p.get("name","").strip().lower() == name.lower():
            return p

    # substring match
    for p in products:
        if name.lower() in p.get("name","").strip().lower():
            return p

    # fuzzy match using difflib
    names = [p.get("name","") for p in products]
    matches = difflib.get_close_matches(name, names, n=1, cutoff=cutoff)
    if matches:
        matched_name = matches[0]
        for p in products:
            if p.get("name","") == matched_name:
                return p
    return None

# ---------- Display helpers ----------
def show_products(products):
    if not products:
        print("No products loaded.")
        return
    print("\nProducts:")
    for p in products:
        print(f" - {p.get('name')}  |  Price: ₹{p.get('price')}  |  Stock: {p.get('stock')}")
    print()

def show_product(product):
    if not product:
        print("Product not found.")
        return
    print(f"\n{product.get('name')}")
    print(f" Price: ₹{product.get('price')}")
    print(f" Stock: {product.get('stock')}\n")

def show_sales(sales, filter_name=None):
    if not sales:
        print("No sales recorded yet.")
        return
    items = sales
    if filter_name:
        items = [s for s in sales if filter_name.lower() in s.get("product_name","").lower()]
    if not items:
        print("No sales match that query.")
        return
    print("\nSales:")
    for s in reversed(items):
        print(f"{s['invoice_number']} | {s['product_name']} x{s['quantity']} @₹{s['unit_price']} = ₹{s['total']} | {s['payment_method']} | {s['date']}")
    print()

# ---------- Sale recording ----------
def record_sale(product, qty, payment_method, products_raw):
    qty = int(qty)
    if qty <= 0:
        print("Quantity must be positive.")
        return None
    stock = product.get("stock", 0)
    if qty > stock:
        print(f"Not enough stock. Available: {stock}")
        return None

    unit_price = product.get("price", 0)
    total = unit_price * qty
    invoice = {
        "invoice_number": create_invoice_number(),
        "product_name": product.get("name"),
        "quantity": qty,
        "unit_price": unit_price,
        "total": total,
        "payment_method": payment_method,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # update stock in products_raw (which might be list)
    product["stock"] = stock - qty
    # save products: if original product.json was a single object, write object; else list
    if isinstance(products_raw, dict):
        # products_raw was the raw dict (single object)
        save_json(PRODUCT_FILE, product)
    else:
        # load current list and save it
        save_json(PRODUCT_FILE, products_raw)

    # append to sale history
    sales_raw = load_json(SALE_FILE, default=None)
    sales = ensure_sales_list(sales_raw)
    sales.append(invoice)
    save_json(SALE_FILE, sales)

    print("\nSale recorded:", invoice["invoice_number"])
    print(f"{product.get('name')} x{qty} | Total ₹{total}\n")
    return invoice

# ---------- Simple NLU (pattern matching) ----------
def parse_and_handle(user, state):
    """
    state: dict with keys products_raw, products_list, last_selected_product (object or None), last_sales
    """
    products_raw = state["products_raw"]
    products_list = state["products_list"]
    last_product = state.get("last_selected_product")
    sales = state["last_sales"]

    u = user.strip()
    if not u:
        return

    # common commands
    low = u.lower()
    if low in ("help","?"):
        print_help()
        return
    if low in ("exit","quit"):
        print("Goodbye!")
        raise SystemExit()
    if low in ("show products","list products","products"):
        show_products(products_list)
        return
    if low.startswith("show sales") or low.startswith("sales"):
        # "show sales", "sales for Galaxy A-17"
        m = re.match(r"sales(?:\s+for\s+(.+))?", u, re.I)
        name = m.group(1) if m else None
        show_sales(sales, name)
        return
    if low in ("show last sale","last sale"):
        if sales:
            show_sales([sales[-1]])
        else:
            print("No sales yet.")
        return
    if low.startswith("show ") or low.startswith("price of ") or low.startswith("how many "):
        # try to extract product name
        # patterns: "show Galaxy A-17", "price of <name>", "how many <name> in stock"
        m = re.match(r"(?:show|price of|how many|what is the price of)\s+(.+)", u, re.I)
        if m:
            name = m.group(1).strip()
            p = find_product_by_name(products_list, name)
            if p:
                show_product(p)
                state["last_selected_product"] = p
            else:
                print("Product not found.")
            return

    # sell patterns: "sell 2 Galaxy A-17" or "sell Galaxy A-17 2" or "2 Galaxy A-17"
    m = re.match(r"sell\s+(\d+)\s+(.+)", u, re.I) or re.match(r"sell\s+(.+?)\s+(\d+)$", u, re.I)
    if m:
        if m.groups() and len(m.groups()) == 2:
            g1, g2 = m.group(1), m.group(2)
            if g1.isdigit():
                qty, name = int(g1), g2.strip()
            elif g2.isdigit():
                qty, name = int(g2), g1.strip()
            else:
                print("Couldn't parse quantity.")
                return
            p = find_product_by_name(products_list, name)
            if not p:
                print("Product not found.")
                return
            pm = input("Payment method (CASH/CARD/UPI) [CASH]: ").strip().upper() or "CASH"
            invoice = record_sale(p, qty, pm, products_raw if isinstance(products_raw, list) else products_list)
            if invoice:
                state["last_sales"] = load_json(SALE_FILE, default=[])
                state["last_selected_product"] = p
            return

    # pattern: "<qty> <product>" e.g. "2 Galaxy A-17"
    m = re.match(r"^(\d+)\s+(.+)$", u)
    if m:
        qty = int(m.group(1))
        name = m.group(2).strip()
        p = find_product_by_name(products_list, name)
        if p:
            pm = input("Payment method (CASH/CARD/UPI) [CASH]: ").strip().upper() or "CASH"
            invoice = record_sale(p, qty, pm, products_raw if isinstance(products_raw, list) else products_list)
            if invoice:
                state["last_sales"] = load_json(SALE_FILE, default=[])
                state["last_selected_product"] = p
            return
        else:
            # maybe user typed quantity to sell of last selected product: "10" only
            if last_product:
                # but since they typed "10 SomeName" and product not found, inform
                print("Product not found. Try 'show products' to see names.")
                return
            print("Product not found.")
            return

    # pattern: only a number -> sell that qty of last selected product
    if re.match(r"^\d+$", u):
        qty = int(u)
        if not last_product:
            print("No product selected. Type product name first or use 'sell <qty> <product>'.")
            return
        pm = input("Payment method (CASH/CARD/UPI) [CASH]: ").strip().upper() or "CASH"
        invoice = record_sale(last_product, qty, pm, products_raw if isinstance(products_raw, list) else products_list)
        if invoice:
            state["last_sales"] = load_json(SALE_FILE, default=[])
            state["last_selected_product"] = last_product
        return

    # user typed product name to select/view
    p = find_product_by_name(products_list, u)
    if p:
        show_product(p)
        state["last_selected_product"] = p
        return

    # ask about sales for a product: "sales for Galaxy A-17"
    m = re.match(r"sales\s+for\s+(.+)", u, re.I)
    if m:
        name = m.group(1).strip()
        show_sales(sales, name)
        return

    # fallback: AI-style reply (simple)
    print("Sorry — I didn't understand. Try 'help' to see available commands, or 'show products'.")

def print_help():
    print("""
Available:
 - show products / list products
 - show <product name>        (shows and selects product)
 - <product name>             (same as above)
 - <number>                   (sell that quantity of selected product)
 - sell <qty> <product>       (sell directly)
 - sell <product> <qty>       (also accepted)
 - show sales                 (list all sales)
 - sales for <product>        (sales filtered by product)
 - last sale                  (show most recent)
 - help, exit
""")

# ---------- Main ----------
def main():
    # ensure files exist with sensible defaults
    if not os.path.exists(PRODUCT_FILE):
        save_json(PRODUCT_FILE, {"name": "Galaxy A-17", "price": 20000, "stock": 20})
    if not os.path.exists(SALE_FILE):
        save_json(SALE_FILE, [])

    products_raw = load_json(PRODUCT_FILE)
    products_list = normalize_products(products_raw)
    sales = ensure_sales_list(load_json(SALE_FILE))

    state = {
        "products_raw": products_raw,
        "products_list": products_list,
        "last_selected_product": products_list[0] if len(products_list)==1 else None,
        "last_sales": sales
    }

    print("Welcome — AI Shop Chatbot (type 'help' for commands)\n")
    show_products(products_list)

    try:
        while True:
            user = input("You: ").strip()
            try:
                parse_and_handle(user, state)
            except SystemExit:
                break
    except KeyboardInterrupt:
        print("\nBye!")

if __name__ == "__main__":
    main()
