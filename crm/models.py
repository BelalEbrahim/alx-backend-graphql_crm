from decimal import Decimal
from django.db import models
from django.utils import timezone


class Customer(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.name} <{self.email}>"


class Product(models.Model):
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)  # must be > 0
    stock = models.PositiveIntegerField(default=0)  # >= 0

    def __str__(self):
        return f"{self.name} (${self.price})"


class Order(models.Model):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="orders")
    products = models.ManyToManyField(Product, related_name="orders")
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"))
    order_date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Order #{self.id} for {self.customer.name} - {self.total_amount}"
