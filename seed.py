"""
Usage:
    python seed_db.py
"""
import os
import django
from decimal import Decimal
from crm.models import Customer, Product, Order

# Point to your Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "graphql_crm.settings")
django.setup()


def recalc_order_total(order: Order) -> None:
    """Recalculate and save order total from its products."""
    total = sum((p.price for p in order.products.all()), Decimal("0.00"))
    order.total_amount = total
    order.save(update_fields=["total_amount"])


def run():
    # Customers
    c1, _ = Customer.objects.get_or_create(
        email="alice@example.com",
        defaults={"name": "Alice", "phone": "+1234567890"},
    )
    c2, _ = Customer.objects.get_or_create(
        email="bob@example.com",
        defaults={"name": "Bob", "phone": "123-456-7890"},
    )

    # Products
    p1, _ = Product.objects.get_or_create(
        name="Laptop",
        defaults={"price": Decimal("999.99"), "stock": 10},
    )
    p2, _ = Product.objects.get_or_create(
        name="Phone",
        defaults={"price": Decimal("499.50"), "stock": 25},
    )
    p3, _ = Product.objects.get_or_create(
        name="Headphones",
        defaults={"price": Decimal("79.90"), "stock": 50},
    )

    # One sample order
    order, created = Order.objects.get_or_create(customer=c1)
    if created or order.products.count() == 0:
        order.products.set([p1, p3])
        recalc_order_total(order)

    print("✅ Seed complete.")
    print(
        f"Customers: {Customer.objects.count()} | "
        f"Products: {Product.objects.count()} | "
        f"Orders: {Order.objects.count()}"
    )


if __name__ == "__main__":
    run()
