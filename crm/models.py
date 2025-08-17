from decimal import Decimal
from django.db import models, transaction
from django.db.models import F, Sum, ExpressionWrapper, DecimalField
from django.utils import timezone
from django.core.validators import MinValueValidator, RegexValidator
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


PHONE_REGEX = RegexValidator(
    regex=r"^\+\d{1,15}$",
    message="Phone number must be in international format, e.g. +15551234567 (max 15 digits).",
)


class Customer(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, validators=[PHONE_REGEX])

    class Meta:
        ordering = ("name",)
        indexes = [models.Index(fields=["email"]), models.Index(fields=["name"])]

    def __str__(self):
        return f"{self.name} <{self.email}>"


class Product(models.Model):
    name = models.CharField(max_length=200)
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],  # must be > 0
    )
    stock = models.PositiveIntegerField(default=0)  # >= 0

    class Meta:
        ordering = ("name",)
        indexes = [models.Index(fields=["name"])]

    def __str__(self):
        return f"{self.name} (${self.price})"


class Order(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_SHIPPED = "shipped"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PAID, "Paid"),
        (STATUS_SHIPPED, "Shipped"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="orders"
    )
    products = models.ManyToManyField(
        Product, through="OrderItem", related_name="orders"
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    order_date = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING
    )

    class Meta:
        ordering = ("-order_date",)
        indexes = [models.Index(fields=["order_date"]), models.Index(fields=["customer"])]

    def __str__(self):
        return f"Order #{self.id or 'unpersisted'} for {self.customer.name} - {self.total_amount}"

    def recalculate_total(self) -> Decimal:
        """
        Recalculate the order total from OrderItem.unit_price * quantity.
        Returns the new total (Decimal) but does NOT save the Order automatically.
        """
        agg = (
            OrderItem.objects.filter(order=self)
            .aggregate(
                total=Sum(
                    ExpressionWrapper(
                        F("unit_price") * F("quantity"),
                        output_field=DecimalField(max_digits=12, decimal_places=2),
                    )
                )
            )
            or {}
        )
        total = agg.get("total") or Decimal("0.00")
        # normalize to 2 decimal places
        total = total.quantize(Decimal("0.01"))
        return total

    def update_total(self, save: bool = True) -> Decimal:
        """
        Recalculate and (optionally) persist the new total_amount.
        Returns the updated total.
        """
        new_total = self.recalculate_total()
        self.total_amount = new_total
        if save:
            # Ensure atomic update
            with transaction.atomic():
                # Use update to avoid triggering signals again (but set on instance too).
                Order.objects.filter(pk=self.pk).update(total_amount=new_total)
        return new_total


class OrderItem(models.Model):
    """
    Through model linking Order <-> Product so we can store quantity and the
    product price at order time (unit_price). This avoids price drift when
    product prices change later.
    """
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField(default=1)
    # snapshot of product price when the item was added to the order
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = (("order", "product"),)
        indexes = [models.Index(fields=["order"]), models.Index(fields=["product"])]

    def __str__(self):
        return f"{self.quantity} x {self.product.name} @ {self.unit_price}"

    @property
    def line_total(self) -> Decimal:
        return (self.unit_price * Decimal(self.quantity)).quantize(Decimal("0.01"))

    def save(self, *args, **kwargs):
        # If unit_price not provided, snapshot the current product price
        if not self.unit_price:
            self.unit_price = self.product.price
        super().save(*args, **kwargs)


# Signal handlers: keep Order.total_amount in sync when items change
@receiver(post_save, sender=OrderItem)
def _orderitem_post_save(sender, instance: OrderItem, **kwargs):
    try:
        instance.order.update_total(save=True)
    except Exception:
        # don't let signal blow up app; better to log in real app
        pass


@receiver(post_delete, sender=OrderItem)
def _orderitem_post_delete(sender, instance: OrderItem, **kwargs):
    try:
        instance.order.update_total(save=True)
    except Exception:
        pass
