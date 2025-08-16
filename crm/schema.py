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
    # Keep GraphQL simple: accept float and cast to Decimal
    price = graphene.Float(required=True)
    stock = graphene.Int(required=False, default_value=0)


class CreateOrderInput(graphene.InputObjectType):
    # Use GraphQL-friendly camelCase names while mapping to Python-style vars
    customer_id = graphene.ID(required=True, name="customerId")
    product_ids = graphene.List(graphene.ID, required=True, name="productIds")
    order_date = graphene.DateTime(
        required=False, name="orderDate")  # optional


# -----------------
# Validators
# -----------------
PHONE_PATTERNS = [
    re.compile(r"^\+\d{7,15}$"),        # +1234567890 (7-15 digits)
    re.compile(r"^\d{3}-\d{3}-\d{4}$"),  # 123-456-7890
]


def valid_phone(p: str) -> bool:
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
        errs = []

        # Uniqueness & validation
        email = (input.email or "").strip().lower()
        name = (input.name or "").strip()
        phone = (input.phone or "").strip() if input.phone else ""

        if not name:
            errs.append("Name is required.")
        if not email:
            errs.append("Email is required.")
        elif Customer.objects.filter(email__iexact=email).exists():
            errs.append("Email already exists.")

        if phone and not valid_phone(phone):
            errs.append(
                "Invalid phone format. Use +1234567890 or 123-456-7890.")

        if errs:
            return CreateCustomer(ok=False, errors=errs, message="Validation failed.", customer=None)

        cust = Customer.objects.create(name=name, email=email, phone=phone)
        return CreateCustomer(ok=True, errors=[], message="Customer created.", customer=cust)


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

        # Track existing + in-batch emails to prevent duplicates
        taken = {e.lower()
                 for e in Customer.objects.values_list("email", flat=True)}

        for i, row in enumerate(input, start=1):
            row_errs = []
            name = (row.name or "").strip()
            email = (row.email or "").strip().lower()
            phone = (row.phone or "").strip() if row.phone else ""

            if not name:
                row_errs.append(f"Row {i}: name is required.")
            if not email:
                row_errs.append(f"Row {i}: email is required.")
            elif email in taken:
                row_errs.append(f"Row {i}: email already exists ({email}).")

            if phone and not valid_phone(phone):
                row_errs.append(f"Row {i}: invalid phone format.")

            if row_errs:
                errors.extend(row_errs)
                continue

            taken.add(email)
            to_create.append(Customer(name=name, email=email, phone=phone))

        # Partial success: create valid rows only, in a single transaction
        if to_create:
            with transaction.atomic():
                created = Customer.objects.bulk_create(to_create)

        return BulkCreateCustomers(ok=len(errors) == 0, errors=errors, customers=created)


class CreateProduct(graphene.Mutation):
    class Arguments:
        input = CreateProductInput(required=True)

    product = graphene.Field(ProductType)
    ok = graphene.Boolean()
    errors = graphene.List(graphene.String)

    @staticmethod
    def mutate(root, info, input: CreateProductInput):
        errs = []

        # Validate & cast price
        try:
            price = Decimal(str(input.price))
        except (InvalidOperation, TypeError):
            price = None
            errs.append("Price must be a number.")

        if price is not None and price <= 0:
            errs.append("Price must be positive.")

        stock = input.stock if input.stock is not None else 0
        if stock < 0:
            errs.append("Stock cannot be negative.")

        name = (input.name or "").strip()
        if not name:
            errs.append("Name is required.")

        if errs:
            return CreateProduct(ok=False, errors=errs, product=None)

        prod = Product.objects.create(name=name, price=price, stock=stock)
        return CreateProduct(ok=True, errors=[], product=prod)


class CreateOrder(graphene.Mutation):
    class Arguments:
        input = CreateOrderInput(required=True)

    order = graphene.Field(OrderType)
    ok = graphene.Boolean()
    errors = graphene.List(graphene.String)

    @staticmethod
    def mutate(root, info, input: CreateOrderInput):
        # Validate customer
        try:
            customer = Customer.objects.get(pk=input.customer_id)
        except Customer.DoesNotExist:
            return CreateOrder(ok=False, errors=[f"Customer ID {input.customer_id} not found."], order=None)

        # Validate products
        ids = list(input.product_ids or [])
        if not ids:
            return CreateOrder(ok=False, errors=["At least one product must be selected."], order=None)

        products = list(Product.objects.filter(pk__in=ids))
        missing = set(map(str, ids)) - {str(p.id) for p in products}
        if missing:
            return CreateOrder(ok=False, errors=[f"Invalid product ID(s): {', '.join(sorted(missing))}"], order=None)

        # Create order atomically and compute total accurately
        with transaction.atomic():
            total = sum((p.price for p in products), Decimal("0.00"))
            order = Order.objects.create(
                customer=customer,
                total_amount=total,
                order_date=input.order_date or timezone.now(),
            )
            order.products.set(products)

        return CreateOrder(ok=True, errors=[], order=order)


# -----------------
# Simple Query (optional helpers)
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
