# crm/tasks.py
from celery import shared_task
from datetime import datetime
from pathlib import Path
import requests

GRAPHQL_URL = "http://localhost:8000/graphql"
LOG_FILE = Path("/tmp/crm_report_log.txt")


@shared_task
def generate_crm_report():
    """
    Fetch totals via GraphQL, then log:
    YYYY-MM-DD HH:MM:SS - Report: X customers, Y orders, Z revenue
    """
    # Simple query: ask for ids (to count) and amounts (to sum).
    # Adjust field names if your schema differs.
    query = """
    query {
      customers { id }
      orders { id totalAmount totalamount }
    }
    """

    try:
        resp = requests.post(GRAPHQL_URL, json={"query": query}, timeout=15)
        data = resp.json().get("data", {})
        customers = data.get("customers") or []
        orders = data.get("orders") or []

        total_customers = len(customers)
        total_orders = len(orders)

        # Sum either `totalAmount` or `totalamount` (whichever your schema uses)
        revenue = 0.0
        for o in orders:
            amt = o.get("totalAmount")
            if amt is None:
                amt = o.get("totalamount")
            try:
                revenue += float(amt or 0)
            except (TypeError, ValueError):
                pass

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts} - Report: {total_customers} customers, {total_orders} orders, {revenue} revenue\n"
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line)

        # Returning a small string is handy when inspecting worker logs
        return "ok"

    except Exception as e:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"{ts} - ERROR: {e}\n")
        return "error"
