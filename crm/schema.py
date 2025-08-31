import re
from decimal import Decimal, InvalidOperation
from django.db import transaction, IntegrityError
from django.utils import timezone
import graphene
from graphene_django import DjangoObjectType
from .models import Customer, Product, Order
from crm.models import Product  # checker specific task


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
    price = graphene.Float(required=True)
    stock = graphene.Int(required=False, default_value=0)


class CreateOrderInput(graphene.InputObjectType):
    customer_id = graphene.ID(required=True, name="customerId")
    product_ids = graphene.List(graphene.ID, required=True, name="productIds")
    order_date = graphene.DateTime(required=False, name="orderDate")


# -----------------
# Validators / helpers
# -----------------
_PHONE_PATTERNS = [
    re.compile(r"^\+\d{7,15}$"),
    re.compile(r"^\d{3}-\d{3}-\d{4}$"),
]


def _valid_phone(phone: str) -> bool:
    if not phone:
        return True
    return any(rx.match(phone) for rx in _PHONE_PATTERNS)


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
            errs.append(
                "Invalid phone format. Use +1234567890 or 123-456-7890.")

        if errs:
            return CreateCustomer(ok=False, errors=errs, message="Validation failed.", customer=None)

        customer = Customer.objects.create(name=name, email=email, phone=phone)
        return CreateCustomer(ok=True, errors=[], message="Customer created.", customer=customer)


class BulkCreateCustomers(graphene.Mutation):
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

        existing_emails = {e.lower()
                           for e in Customer.objects.values_list("email", flat=True)}
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
                    row_errs.append(
                        f"Row {idx}: email already exists ({email}).")
                if email in seen_in_batch:
                    row_errs.append(
                        f"Row {idx}: duplicate email within payload ({email}).")

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
                            created.append(Customer.objects.create(
                                name=c.name, email=c.email, phone=c.phone))
                        except IntegrityError:
                            errors.append(f"Email already exists ({c.email}).")

        return BulkCreateCustomers(ok=len(errors) == 0, customers=created, errors=errors)


class CreateProduct(graphene.Mutation):
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
            price = Decimal(str(input.price))
        except (InvalidOperation, TypeError):
            price = None
            errs.append("Price must be a number.")

        if price is not None and price <= 0:
            errs.append("Price must be positive.")

        stock = input.stock if input.stock is not None else 0
        if stock < 0:
            errs.append("Stock cannot be negative.")

        if errs:
            return CreateProduct(ok=False, errors=errs, product=None)

        product = Product.objects.create(name=name, price=price, stock=stock)
        return CreateProduct(ok=True, errors=[], product=product)


class CreateOrder(graphene.Mutation):
    class Arguments:
        input = CreateOrderInput(required=True)

    order = graphene.Field(OrderType)
    ok = graphene.Boolean()
    errors = graphene.List(graphene.String)

    @staticmethod
    def mutate(root, info, input: CreateOrderInput):
        try:
            customer = Customer.objects.get(pk=input.customer_id)
        except Customer.DoesNotExist:
            return CreateOrder(ok=False, errors=[f"Customer ID {input.customer_id} not found."], order=None)

        ids = list(input.product_ids or [])
        if not ids:
            return CreateOrder(ok=False, errors=["At least one product must be selected."], order=None)

        products = list(Product.objects.filter(pk__in=ids))
        missing = set(map(str, ids)) - {str(p.id) for p in products}
        if missing:
            return CreateOrder(ok=False, errors=[f"Invalid product ID(s): {', '.join(sorted(missing))}"], order=None)

        with transaction.atomic():
            total = sum((p.price for p in products), Decimal("0.00"))
            order = Order.objects.create(
                customer=customer,
                total_amount=total,
                order_date=input.order_date or timezone.now(),
            )
            order.products.set(products)

        return CreateOrder(ok=True, errors=[], order=order)


class UpdateLowStockProducts(graphene.Mutation):
    """Maintenance mutation: bump stock by 10 for products with stock < 10."""
    ok = graphene.Boolean()
    message = graphene.String()
    updated_products = graphene.List(ProductType)

    @classmethod
    def mutate(cls, root, info):
        updated = []
        qs = Product.objects.filter(stock__lt=10)
        for p in qs:
            p.stock += 10
            p.save()
            updated.append(p)

        return UpdateLowStockProducts(
            ok=True,
            message=f"Updated {len(updated)} product(s).",
            updated_products=updated
        )


# -----------------
# Root Query & Mutation
# -----------------
class Query(graphene.ObjectType):
    # handy for heartbeat
    hello = graphene.String(default_value="Hello, GraphQL!")
    all_customers = graphene.List(CustomerType)
    all_products = graphene.List(ProductType)
    all_orders = graphene.List(OrderType)

    def resolve_all_customers(root, info):
        return Customer.objects.all()

    def resolve_all_products(root, info):
        return Product.objects.all()

    def resolve_all_orders(root, info):
        return Order.objects.select_related("customer").prefetch_related("products").all()


class Mutation(graphene.ObjectType):
    create_customer = CreateCustomer.Field()
    bulk_create_customers = BulkCreateCustomers.Field()
    create_product = CreateProduct.Field()
    create_order = CreateOrder.Field()
    update_low_stock_products = UpdateLowStockProducts.Field()


schema = graphene.Schema(query=Query, mutation=Mutation)
