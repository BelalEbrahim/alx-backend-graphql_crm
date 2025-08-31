import datetime
import requests
from gql.transport.requests import RequestsHTTPTransport
from gql import gql, Client


def log_crm_heartbeat():
    """
    Logs heartbeat into /tmp/crm_heartbeat_log.txt.
    Format: DD/MM/YYYY-HH:MM:SS CRM is alive
    Also pings GraphQL { hello } endpoint via requests and gql client.
    """
    now_str = datetime.datetime.now().strftime("%d/%m/%Y-%H:%M:%S")
    log_file = "/tmp/crm_heartbeat_log.txt"

    # Always log heartbeat
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{now_str} CRM is alive\n")

    # --- Raw requests ping ---
    try:
        r = requests.post(
            "http://localhost:8000/graphql",
            json={"query": "{ hello }"},
            timeout=5,
        )
        if r.ok:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write("GraphQL hello (requests) OK\n")
    except Exception:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("GraphQL hello (requests) FAILED\n")

    # --- gql client ping ---
    try:
        transport = RequestsHTTPTransport(
            url="http://localhost:8000/graphql",
            verify=True,
            retries=3,
        )
        client = Client(transport=transport, fetch_schema_from_transport=True)
        gql_query = gql("{ hello }")
        gql_result = client.execute(gql_query)

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"GraphQL hello (gql client) OK: {gql_result}\n")
    except Exception:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("GraphQL hello (gql client) FAILED\n")


def update_low_stock():
    """
    Calls the GraphQL mutation to restock products with stock < 10.
    Logs updated product names + new stock to /tmp/low_stock_updates_log.txt
    """
    mutation = """
    mutation {
      updateLowStockProducts {
        ok
        message
        updatedProducts { name stock }
      }
    }
    """

    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        import requests
        r = requests.post(
            "http://localhost:8000/graphql",
            json={"query": mutation},
            timeout=10,
        )
        data = r.json()
        upd = data.get("data", {}).get("updateLowStockProducts", {})
        products = upd.get("updatedProducts", []) or []

        with open("/tmp/low_stock_updates_log.txt", "a", encoding="utf-8") as f:
            if products:
                for p in products:
                    f.write(f"{ts} {p['name']} -> {p['stock']}\n")
            else:
                f.write(f"{ts} No low-stock products to update\n")
    except Exception as e:
        with open("/tmp/low_stock_updates_log.txt", "a", encoding="utf-8") as f:
            f.write(f"{ts} ERROR: {e}\n")
