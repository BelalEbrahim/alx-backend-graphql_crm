"""
Usage:
    python seed_db.py
"""
from crm.models import Customer, Product, Order
from decimal import Decimal
import os
import django

# Point to your Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "graphql_crm.settings")
django.setup()


def run():
    # Customers
    c1, _ = Customer.objects.get_or_create(
        name="Alice", email="alice@example.com", defaults={"phone": "+1234567890"})
    c2, _ = Customer.objects.get_or_create(
        name="Bob", email="bob@example.com", defaults={"phone": "123-456-7890"})

    # Products
    p1, _ = Product.objects.get_or_create(
        name="Laptop", defaults={"price": Decimal("999.99"), "stock": 10})
    p2, _ = Product.objects.get_or_create(
        name="Phone", defaults={"price": Decimal("499.50"), "stock": 25})
    p3, _ = Product.objects.get_or_create(name="Headphones", defaults={
                                          "price": Decimal("79.90"), "stock": 50})

    # One sample order
    if not Order.objects.exists():
        o = Order.objects.create(customer=c1, total_amount=Decimal("0.00"))
        o.products.set([p1, p3])
        # Recalculate total
        o.total_amount = sum(
            (x.price for x in o.products.all()), Decimal("0.00"))
        o.save()

    print("Seed complete.")
    print(
        f"Customers: {Customer.objects.count()}, Products: {Product.objects.count()}, Orders: {Order.objects.count()}")


if __name__ == "__main__":
    run()
