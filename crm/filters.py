# crm/filters.py
import django_filters as df
from .models import Customer, Product, Order


class CustomerFilter(df.FilterSet):
    # Case-insensitive partials
    name = df.CharFilter(field_name="name", lookup_expr="icontains")
    email = df.CharFilter(field_name="email", lookup_expr="icontains")

    # Date range (created_at)
    created_at__gte = df.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="gte")
    created_at__lte = df.IsoDateTimeFilter(
        field_name="created_at", lookup_expr="lte")

    # Challenge: phone pattern (e.g., starts with +1)
    phone_pattern = df.CharFilter(method="filter_phone_pattern")

    class Meta:
        model = Customer
        fields = ["name", "email", "created_at__gte", "created_at__lte"]

    def filter_phone_pattern(self, queryset, name, value):
        if not value:
            return queryset
        # Example: value="+1" → matches numbers starting with +1
        return queryset.filter(phone__startswith=value)


class ProductFilter(df.FilterSet):
    name = df.CharFilter(field_name="name", lookup_expr="icontains")

    # Ranges
    price__gte = df.NumberFilter(field_name="price", lookup_expr="gte")
    price__lte = df.NumberFilter(field_name="price", lookup_expr="lte")

    stock = df.NumberFilter(field_name="stock", lookup_expr="exact")
    stock__gte = df.NumberFilter(field_name="stock", lookup_expr="gte")
    stock__lte = df.NumberFilter(field_name="stock", lookup_expr="lte")

    # Think: low stock → use a param like stock_lt (e.g., 10)
    stock__lt = df.NumberFilter(field_name="stock", lookup_expr="lt")

    class Meta:
        model = Product
        fields = ["name", "price__gte", "price__lte",
                  "stock", "stock__gte", "stock__lte", "stock__lt"]


class OrderFilter(df.FilterSet):
    # Totals & dates
    total_amount__gte = df.NumberFilter(
        field_name="total_amount", lookup_expr="gte")
    total_amount__lte = df.NumberFilter(
        field_name="total_amount", lookup_expr="lte")
    order_date__gte = df.IsoDateTimeFilter(
        field_name="order_date", lookup_expr="gte")
    order_date__lte = df.IsoDateTimeFilter(
        field_name="order_date", lookup_expr="lte")

    # Related lookups
    customer_name = df.CharFilter(
        field_name="customer__name", lookup_expr="icontains")
    product_name = df.CharFilter(
        field_name="products__name", lookup_expr="icontains")

    # Challenge: include specific product id
    product_id = df.NumberFilter(
        field_name="products__id", lookup_expr="exact")

    class Meta:
        model = Order
        fields = [
            "total_amount__gte", "total_amount__lte",
            "order_date__gte", "order_date__lte",
            "customer_name", "product_name", "product_id",
        ]

    # Avoid duplicates from M2M joins
    @property
    def qs(self):
        return super().qs.distinct()
