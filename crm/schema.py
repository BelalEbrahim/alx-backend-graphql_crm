# crm/schema.py
from decimal import Decimal
import graphene
from graphene import relay
from graphene_django import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
from django_filters.utils import translate_validation
from .models import Customer, Product, Order
from .filters import CustomerFilter, ProductFilter, OrderFilter


# -----------------
# GraphQL Types (Relay)
# -----------------
class CustomerType(DjangoObjectType):
    class Meta:
        model = Customer
        interfaces = (relay.Node,)
        fields = ("id", "name", "email", "phone", "created_at")


class ProductType(DjangoObjectType):
    class Meta:
        model = Product
        interfaces = (relay.Node,)
        fields = ("id", "name", "price", "stock")


class OrderType(DjangoObjectType):
    class Meta:
        model = Order
        interfaces = (relay.Node,)
        fields = ("id", "customer", "products", "total_amount", "order_date")


# -----------------
# Filter Input Objects (camelCase for GraphQL)
# -----------------
class CustomerFilterInput(graphene.InputObjectType):
    nameIcontains = graphene.String()
    emailIcontains = graphene.String()
    createdAtGte = graphene.DateTime()
    createdAtLte = graphene.DateTime()
    phonePattern = graphene.String()  # e.g., "+1"


class ProductFilterInput(graphene.InputObjectType):
    nameIcontains = graphene.String()
    priceGte = graphene.Float()
    priceLte = graphene.Float()
    stockGte = graphene.Int()
    stockLte = graphene.Int()
    stockLt = graphene.Int()  # low stock helper


class OrderFilterInput(graphene.InputObjectType):
    totalAmountGte = graphene.Float()
    totalAmountLte = graphene.Float()
    orderDateGte = graphene.DateTime()
    orderDateLte = graphene.DateTime()
    customerName = graphene.String()
    productName = graphene.String()
    productId = graphene.ID()


# -----------------
# Helpers: map input → django-filter kwargs; apply ordering safely
# -----------------
def _apply_ordering(qs, order_by, allowed):
    if not order_by:
        return qs
    # Allow multiple fields, validate against whitelist
    normalized = []
    for item in order_by:
        if not item:
            continue
        desc = item.startswith("-")
        key = item[1:] if desc else item
        # map camelCase → snake_case
        key_snake = (
            key.replace("createdAt", "created_at")
               .replace("orderDate", "order_date")
               .replace("totalAmount", "total_amount")
        )
        if key_snake not in allowed:
            # ignore unknown fields
            continue
        normalized.append(f"-{key_snake}" if desc else key_snake)
    return qs.order_by(*normalized) if normalized else qs


def _customer_filter_kwargs(f: CustomerFilterInput):
    d = {}
    if f is None:
        return d
    if f.nameIcontains is not None:
        # we’ll pass into FilterSet as name (icontains set in FilterSet)
        d["name"] = f.nameIcontains
    if f.emailIcontains is not None:
        d["email"] = f.emailIcontains
    if f.createdAtGte is not None:
        d["created_at__gte"] = f.createdAtGte
    if f.createdAtLte is not None:
        d["created_at__lte"] = f.createdAtLte
    if f.phonePattern is not None:
        d["phone_pattern"] = f.phonePattern
    return d


def _product_filter_kwargs(f: ProductFilterInput):
    d = {}
    if f is None:
        return d
    if f.nameIcontains is not None:
        d["name"] = f.nameIcontains
    if f.priceGte is not None:
        d["price__gte"] = f.priceGte
    if f.priceLte is not None:
        d["price__lte"] = f.priceLte
    if f.stockGte is not None:
        d["stock__gte"] = f.stockGte
    if f.stockLte is not None:
        d["stock__lte"] = f.stockLte
    if f.stockLt is not None:
        d["stock__lt"] = f.stockLt
    return d


def _order_filter_kwargs(f: OrderFilterInput):
    d = {}
    if f is None:
        return d
    if f.totalAmountGte is not None:
        d["total_amount__gte"] = f.totalAmountGte
    if f.totalAmountLte is not None:
        d["total_amount__lte"] = f.totalAmountLte
    if f.orderDateGte is not None:
        d["order_date__gte"] = f.orderDateGte
    if f.orderDateLte is not None:
        d["order_date__lte"] = f.orderDateLte
    if f.customerName is not None:
        d["customer_name"] = f.customerName
    if f.productName is not None:
        d["product_name"] = f.productName
    if f.productId is not None:
        d["product_id"] = f.productId
    return d


# -----------------
# Query with filtered connections
# -----------------
class Query(graphene.ObjectType):
    # We keep DjangoFilterConnectionField (required) but add our own
    # `filter` input and `orderBy` list, then resolve using the FilterSet.
    all_customers = DjangoFilterConnectionField(
        CustomerType,
        filter=CustomerFilterInput(),
        order_by=graphene.List(graphene.String, name="orderBy"),
    )

    all_products = DjangoFilterConnectionField(
        ProductType,
        filter=ProductFilterInput(),
        order_by=graphene.List(graphene.String, name="orderBy"),
    )

    all_orders = DjangoFilterConnectionField(
        OrderType,
        filter=OrderFilterInput(),
        order_by=graphene.List(graphene.String, name="orderBy"),
    )

    # Resolvers apply FilterSet + ordering
    def resolve_all_customers(root, info, **kwargs):
        f_input = kwargs.get("filter")
        order_by = kwargs.get("order_by")
        data = _customer_filter_kwargs(f_input)
        qs = CustomerFilter(data=data, queryset=Customer.objects.all()).qs
        qs = _apply_ordering(qs, order_by, allowed={
                             "name", "email", "created_at"})
        return qs

    def resolve_all_products(root, info, **kwargs):
        f_input = kwargs.get("filter")
        order_by = kwargs.get("order_by")
        data = _product_filter_kwargs(f_input)
        qs = ProductFilter(data=data, queryset=Product.objects.all()).qs
        qs = _apply_ordering(qs, order_by, allowed={"name", "price", "stock"})
        return qs

    def resolve_all_orders(root, info, **kwargs):
        f_input = kwargs.get("filter")
        order_by = kwargs.get("order_by")
        data = _order_filter_kwargs(f_input)
        qs = OrderFilter(data=data, queryset=Order.objects.select_related(
            "customer").prefetch_related("products")).qs
        qs = _apply_ordering(qs, order_by, allowed={
                             "order_date", "total_amount", "customer__name"})
        return qs


# class Mutation(graphene.ObjectType):
#     create_customer = CreateCustomer.Field()
#     bulk_create_customers = BulkCreateCustomers.Field()
#     create_product = CreateProduct.Field()
#     create_order = CreateOrder.Field()
