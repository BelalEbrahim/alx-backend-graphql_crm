#!/usr/bin/env python3
"""Send reminders for recent orders via GraphQL and log them."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

GRAPHQL_URL = "http://localhost:8000/graphql"
LOG_FILE = Path("/tmp/order_reminders_log.txt")

client = Client(
    transport=RequestsHTTPTransport(url=GRAPHQL_URL, timeout=10),
    fetch_schema_from_transport=False
)

query = gql("""
query {
  orders {
    id
    orderDate
    status
    customer { email }
  }
}
""")


def is_recent(dt_str: str) -> bool:
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt >= datetime.now(timezone.utc) - timedelta(days=7)
    except Exception:
        return False


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    orders = client.execute(query).get("orders", [])

    reminders = [
        f"{now} Reminder -> Order {o.get('id')} / {(o.get('customer') or {}).get('email', 'unknown@example.com')}"
        for o in orders
        if o and is_recent(o.get("orderDate", ""))
    ]

    if reminders:
        LOG_FILE.write_text("\n".join(reminders) + "\n",
                            encoding="utf-8", append=True)

    print("Order reminders processed!")


if __name__ == "__main__":
    main()
