# crm/schema.py
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django.db import transaction, IntegrityError
from django.db.models import F
from django.utils import timezone
import graphene
from graphene_django import DjangoObjectType
from .models import Customer, Product, Order, OrderItem

# -----------------
# GraphQL Types
# -----------------
class CustomerType(DjangoObjectType):
    class Meta:
        model = Customer
        fields = ("id", "name", "email", "phone")


class ProductType(DjangoObjectType):
    class Meta:
        model = Product
        fields = ("id", "name", "price", "stock")


class OrderItemType(DjangoObjectType):
    class Meta:
        model = OrderItem
        fields = ("id", "product", "quantity", "unit_price", "order")


class OrderType(DjangoObjectType):
    class Meta:
        model = Order
        fields = ("id", "customer", "items", "total_amount", "order_date", "status")


# -----------------
# Inputs
# -----------------
class CreateCustomerInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    email = graphene.String(required=True)
    phone = graphene.String(required=False)


class CreateProductInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    price = graphene.Float(required=True)
    stock = graphene.Int(required=False, default_value=0)


class OrderItemInput(graphene.InputObjectType):
    product_id = graphene.ID(required=True, name="productId")
    quantity = graphene.Int(required=False, default_value=1)


class CreateOrderInput(graphene.InputObjectType):
    customer_id = graphene.ID(required=True, name="customerId")
    items = graphene.List(OrderItemInput, required=True)
    order_date = graphene.DateTime(required=False, name="orderDate")


# -----------------
# Simple validators / helpers
# -----------------
_PHONE_PATTERNS = [
    re.compile(r"^\+\d{7,15}$"),         # +1234567890  (7–15 digits)
    re.compile(r"^\d{3}-\d{3}-\d{4}$"),  # 123-456-7890
]


def _valid_phone(phone: str) -> bool:
    if not phone:
        return True
    return any(rx.match(phone) for rx in _PHONE_PATTERNS)


def _to_decimal(value) -> Decimal:
    """Safely convert numeric input to Decimal with 2 decimal places."""
    d = Decimal(str(value))
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# -----------------
# Mutations
# -----------------
class CreateCustomer(graphene.Mutation):
    """Create a single customer with validation and friendly errors."""
    class Arguments:
        input = CreateCustomerInput(required=True)

    customer = graphene.Field(CustomerType)
    message = graphene.String()
    ok = graphene.Boolean()
    errors = graphene.List(graphene.String)

    @staticmethod
    def mutate(root, info, input: CreateCustomerInput):
        errs = []

        name = (input.name or "").strip()
        email = (input.email or "").strip().lower()
        phone = (input.phone or "").strip() if input.phone else ""

        if not name:
            errs.append("Name is required.")
        if not email:
            errs.append("Email is required.")
        elif Customer.objects.filter(email__iexact=email).exists():
            errs.append("Email already exists.")
        if phone and not _valid_phone(phone):
            errs.append("Invalid phone format. Use +1234567890 or 123-456-7890.")

        if errs:
            return CreateCustomer(ok=False, errors=errs, message="Validation failed.", customer=None)

        customer = Customer.objects.create(name=name, email=email, phone=phone)
        return CreateCustomer(ok=True, errors=[], message="Customer created.", customer=customer)


class BulkCreateCustomers(graphene.Mutation):
    """
    Bulk create customers with per-row validation.
    Partial success supported: valid rows are created, invalid rows are reported.
    """
    class Arguments:
        input = graphene.List(CreateCustomerInput, required=True)

    customers = graphene.List(CustomerType)
    errors = graphene.List(graphene.String)
    ok = graphene.Boolean()

    @staticmethod
    def mutate(root, info, input):
        if not input:
            return BulkCreateCustomers(ok=False, customers=[], errors=["No customers provided."])

        errors = []
        to_create = []
        created = []

        existing_emails = {e.lower() for e in Customer.objects.values_list("email", flat=True)}
        seen_in_batch = set()

        for idx, row in enumerate(input, start=1):
            row_errs = []
            name = (row.name or "").strip()
            email = (row.email or "").strip().lower()
            phone = (row.phone or "").strip() if row.phone else ""

            if not name:
                row_errs.append(f"Row {idx}: name is required.")
            if not email:
                row_errs.append(f"Row {idx}: email is required.")
            else:
                if email in existing_emails:
                    row_errs.append(f"Row {idx}: email already exists ({email}).")
                if email in seen_in_batch:
                    row_errs.append(f"Row {idx}: duplicate email within payload ({email}).")

            if phone and not _valid_phone(phone):
                row_errs.append(f"Row {idx}: invalid phone format.")

            if row_errs:
                errors.extend(row_errs)
                continue

            seen_in_batch.add(email)
            to_create.append(Customer(name=name, email=email, phone=phone))

        if to_create:
            try:
                with transaction.atomic():
                    created = Customer.objects.bulk_create(to_create)
            except IntegrityError:
                created = []
                with transaction.atomic():
                    for c in to_create:
                        try:
                            created.append(Customer.objects.create(name=c.name, email=c.email, phone=c.phone))
                        except IntegrityError:
                            errors.append(f"Email already exists ({c.email}).")

        return BulkCreateCustomers(ok=len(errors) == 0, customers=created, errors=errors)


class CreateProduct(graphene.Mutation):
    """Create a product; price > 0, stock >= 0."""
    class Arguments:
        input = CreateProductInput(required=True)

    product = graphene.Field(ProductType)
    ok = graphene.Boolean()
    errors = graphene.List(graphene.String)

    @staticmethod
    def mutate(root, info, input: CreateProductInput):
        errs = []

        name = (input.name or "").strip()
        if not name:
            errs.append("Name is required.")

        try:
            price = _to_decimal(input.price)
        except (InvalidOperation, TypeError, ValueError):
            price = None
            errs.append("Price must be a valid number.")

        if price is not None and price <= Decimal("0.00"):
            errs.append("Price must be positive.")

        stock = input.stock if input.stock is not None else 0
        if stock < 0:
            errs.append("Stock cannot be negative.")

        if errs:
            return CreateProduct(ok=False, errors=errs, product=None)

        product = Product.objects.create(name=name, price=price, stock=stock)
        return CreateProduct(ok=True, errors=[], product=product)


class CreateOrder(graphene.Mutation):
    """
    Create an order with items:
    - customer_id must exist
    - items must be non-empty list of {product_id, quantity}
    - checks stock, decrements stock atomically, snapshots unit_price per item
    """
    class Arguments:
        input = CreateOrderInput(required=True)

    order = graphene.Field(OrderType)
    ok = graphene.Boolean()
    errors = graphene.List(graphene.String)

    @staticmethod
    def mutate(root, info, input: CreateOrderInput):
        errors = []

        # Validate customer
        try:
            customer = Customer.objects.get(pk=input.customer_id)
        except Customer.DoesNotExist:
            return CreateOrder(ok=False, errors=[f"Customer ID {input.customer_id} not found."], order=None)

        items_in = list(input.items or [])
        if not items_in:
            return CreateOrder(ok=False, errors=["At least one item is required."], order=None)

        # Normalize requested product ids and quantities
        requested = {}
        for idx, it in enumerate(items_in, start=1):
            try:
                pid = int(it.product_id)
            except (TypeError, ValueError):
                errors.append(f"Item {idx}: invalid productId '{it.product_id}'.")
                continue
            qty = int(it.quantity) if it.quantity is not None else 1
            if qty <= 0:
                errors.append(f"Item {idx}: quantity must be >= 1.")
                continue
            requested[pid] = requested.get(pid, 0) + qty

        if errors:
            return CreateOrder(ok=False, errors=errors, order=None)

        # Fetch products and lock rows for update to avoid races when decreasing stock
        products = list(Product.objects.filter(pk__in=requested.keys()))
        found_ids = {p.id for p in products}
        missing = set(requested.keys()) - found_ids
        if missing:
            return CreateOrder(ok=False, errors=[f"Invalid product ID(s): {', '.join(map(str, sorted(missing)))}"], order=None)

        with transaction.atomic():
            # re-fetch with select_for_update
            products_for_update = {p.id: p for p in Product.objects.select_for_update().filter(pk__in=requested.keys())}

            # Check stock availability
            stock_errors = []
            for pid, qty in requested.items():
                prod = products_for_update.get(pid)
                if prod.stock < qty:
                    stock_errors.append(f"Product {prod.name} (id={pid}) has insufficient stock ({prod.stock} < {qty}).")
            if stock_errors:
                return CreateOrder(ok=False, errors=stock_errors, order=None)

            # Create order
            order = Order.objects.create(
                customer=customer,
                total_amount=Decimal("0.00"),
                order_date=input.order_date or timezone.now(),
            )

            # Create OrderItems (snapshot unit_price) and decrement stock
            items_created = []
            for pid, qty in requested.items():
                prod = products_for_update[pid]
                unit_price = prod.price
                # Create order item
                oi = OrderItem.objects.create(order=order, product=prod, quantity=qty, unit_price=unit_price)
                items_created.append(oi)
                # decrement stock
                prod.stock = F("stock") - qty
                prod.save(update_fields=["stock"])

            # Refresh product objects so stock values are accurate if needed later
            for p in products_for_update.values():
                p.refresh_from_db(fields=["stock"])

            # Recalculate & persist total
            order.update_total(save=True)

        return CreateOrder(ok=True, errors=[], order=order)


# -----------------
# Root Query & Mutation
# -----------------
class Query(graphene.ObjectType):
    customers = graphene.List(CustomerType)
    products = graphene.List(ProductType)
    orders = graphene.List(OrderType)

    def resolve_customers(root, info):
        return Customer.objects.all()

    def resolve_products(root, info):
        return Product.objects.all()

    def resolve_orders(root, info):
        return Order.objects.select_related("customer").prefetch_related("items__product").all()


class Mutation(graphene.ObjectType):
    create_customer = CreateCustomer.Field()
    bulk_create_customers = BulkCreateCustomers.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()
