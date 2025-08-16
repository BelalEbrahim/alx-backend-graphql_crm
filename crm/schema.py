import re
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.utils import timezone
import graphene
from graphene_django import DjangoObjectType
from .models import Customer, Product, Order

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


class OrderType(DjangoObjectType):
    class Meta:
        model = Order
        fields = ("id", "customer", "products", "total_amount", "order_date")


# -----------------
# Inputs
# -----------------
class CreateCustomerInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    email = graphene.String(required=True)
    phone = graphene.String(required=False)


class CreateProductInput(graphene.InputObjectType):
    name = graphene.String(required=True)
    # Using Float for simplicity; we convert to Decimal safely
    price = graphene.Float(required=True)
    stock = graphene.Int(required=False, default_value=0)


class CreateOrderInput(graphene.InputObjectType):
    customer_id = graphene.ID(required=True)
    product_ids = graphene.List(graphene.ID, required=True)
    # defaults to now if not given
    order_date = graphene.DateTime(required=False)


# -----------------
# Validators
# -----------------
PHONE_PATTERNS = [
    re.compile(r"^\+\d{7,15}$"),       # +1234567890   (7-15 digits)
    re.compile(r"^\d{3}-\d{3}-\d{4}$")  # 123-456-7890
]


def is_valid_phone(p: str) -> bool:
    if not p:
        return True
    return any(rx.match(p) for rx in PHONE_PATTERNS)

# -----------------
# Mutations
# -----------------


class CreateCustomer(graphene.Mutation):
    class Arguments:
        input = CreateCustomerInput(required=True)

    customer = graphene.Field(CustomerType)
    message = graphene.String()
    ok = graphene.Boolean()
    errors = graphene.List(graphene.String)

    @staticmethod
    def mutate(root, info, input: CreateCustomerInput):
        errors = []

        # Unique email
        if Customer.objects.filter(email__iexact=input.email).exists():
            errors.append("Email already exists.")

        # Phone validation
        if input.phone and not is_valid_phone(input.phone):
            errors.append(
                "Invalid phone format. Use +1234567890 or 123-456-7890.")

        if errors:
            return CreateCustomer(ok=False, errors=errors, message="Validation failed.")

        customer = Customer.objects.create(
            name=input.name.strip(),
            email=input.email.strip().lower(),
            phone=(input.phone or "").strip(),
        )
        return CreateCustomer(customer=customer, ok=True, message="Customer created.")


class BulkCreateCustomers(graphene.Mutation):
    class Arguments:
        input = graphene.List(CreateCustomerInput, required=True)

    customers = graphene.List(CustomerType)
    errors = graphene.List(graphene.String)
    ok = graphene.Boolean()

    @staticmethod
    def mutate(root, info, input):
        if not input:
            return BulkCreateCustomers(ok=False, errors=["No customers provided."], customers=[])

        errors = []
        to_create = []
        created = []
        seen_emails = set(
            Customer.objects.values_list("email", flat=True)
        )  # existing emails to avoid duplicates

        # Validate each row
        for idx, row in enumerate(input, start=1):
            row_errors = []
            name = (row.name or "").strip()
            email = (row.email or "").strip().lower()
            phone = (row.phone or "").strip() if row.phone else ""

            if not name:
                row_errors.append(f"Row {idx}: name is required.")
            if not email:
                row_errors.append(f"Row {idx}: email is required.")
            elif email in seen_emails:
                row_errors.append(
                    f"Row {idx}: email already exists ({email}).")

            if phone and not is_valid_phone(phone):
                row_errors.append(f"Row {idx}: invalid phone format.")

            if row_errors:
                errors.extend(row_errors)
                continue

            # Mark as "will insert"
            seen_emails.add(email)
            to_create.append(Customer(name=name, email=email, phone=phone))

        # Create valid ones in one transaction (partial success supported)
        if to_create:
            with transaction.atomic():
                created = Customer.objects.bulk_create(
                    to_create, ignore_conflicts=True)

        return BulkCreateCustomers(
            ok=len(errors) == 0,
            customers=created,
            errors=errors
        )


class CreateProduct(graphene.Mutation):
    class Arguments:
        input = CreateProductInput(required=True)

    product = graphene.Field(ProductType)
    ok = graphene.Boolean()
    errors = graphene.List(graphene.String)

    @staticmethod
    def mutate(root, info, input: CreateProductInput):
        errors = []
        # Validate price
        try:
            price = Decimal(str(input.price))
        except (InvalidOperation, TypeError):
            errors.append("Price must be a number.")
            price = None

        if price is not None and price <= 0:
            errors.append("Price must be positive.")

        stock = input.stock if input.stock is not None else 0
        if stock < 0:
            errors.append("Stock cannot be negative.")

        if errors:
            return CreateProduct(ok=False, errors=errors)

        product = Product.objects.create(
            name=input.name.strip(), price=price, stock=stock)
        return CreateProduct(product=product, ok=True, errors=[])


class CreateOrder(graphene.Mutation):
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

        # Validate product IDs
        ids = list(input.product_ids or [])
        if not ids:
            return CreateOrder(ok=False, errors=["At least one product must be selected."], order=None)

        products = list(Product.objects.filter(pk__in=ids))
        missing = set(map(str, ids)) - set(map(lambda p: str(p.id), products))
        if missing:
            return CreateOrder(ok=False, errors=[f"Invalid product ID(s): {', '.join(sorted(missing))}"], order=None)

        # Create order atomically
        with transaction.atomic():
            # Compute total
            total = sum((p.price for p in products), Decimal("0.00"))

            order = Order.objects.create(
                customer=customer,
                total_amount=total,
                order_date=input.order_date or timezone.now(),
            )
            order.products.set(products)

        return CreateOrder(order=order, ok=True, errors=[])


# -----------------
# Query (simple lists)
# -----------------
class Query(graphene.ObjectType):
    customers = graphene.List(CustomerType)
    products = graphene.List(ProductType)
    orders = graphene.List(OrderType)

    def resolve_customers(root, info):
        return Customer.objects.all().order_by("id")

    def resolve_products(root, info):
        return Product.objects.all().order_by("id")

    def resolve_orders(root, info):
        return Order.objects.select_related("customer").prefetch_related("products").order_by("id")


# -----------------
# Root Mutation
# -----------------
class Mutation(graphene.ObjectType):
    create_customer = CreateCustomer.Field()
    bulk_create_customers = BulkCreateCustomers.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()
