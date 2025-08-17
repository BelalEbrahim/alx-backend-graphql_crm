# crm/filters.py
import re
import django_filters as filters
from .models import Customer, Product, Order


_REGEXP_CHARS = set("^$*+?[](){}|\\")  # naive check for regex-like input


class CustomerFilter(filters.FilterSet):
    """Filters for Customer model: name/email partials, created_at range, and phone patterns."""

    # Case-insensitive partial matches
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    email = filters.CharFilter(field_name="email", lookup_expr="icontains")

    # Date range (created_at)
    created_at__gte = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at__lte = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    # Phone pattern: either a simple prefix (e.g. "+1") or a regex if the value contains regex chars.
    phone_pattern = filters.CharFilter(method="filter_phone_pattern")

    class Meta:
        model = Customer
        fields = ["name", "email", "created_at__gte", "created_at__lte", "phone_pattern"]

    def filter_phone_pattern(self, queryset, name, value):
        """If `value` looks like a regex (contains regexp chars) use iregex,
        otherwise treat it as a startswith prefix."""
        if not value:
            return queryset
        value = value.strip()
        if any((c in value) for c in _REGEXP_CHARS):
            # treat as case-insensitive regex
            try:
                re.compile(value)
            except re.error:
                # invalid regex: fall back to startswith
                return queryset.filter(phone__startswith=value)
            return queryset.filter(phone__iregex=value)
        # simple prefix match
        return queryset.filter(phone__startswith=value)


class ProductFilter(filters.FilterSet):
    """Filters for Product model: name partial, price ranges, stock ranges, and in-stock helper."""

    name = filters.CharFilter(field_name="name", lookup_expr="icontains")

    # Price ranges
    price__gte = filters.NumberFilter(field_name="price", lookup_expr="gte")
    price__lte = filters.NumberFilter(field_name="price", lookup_expr="lte")

    # Stock exact & ranges
    stock = filters.NumberFilter(field_name="stock", lookup_expr="exact")
    stock__gte = filters.NumberFilter(field_name="stock", lookup_expr="gte")
    stock__lte = filters.NumberFilter(field_name="stock", lookup_expr="lte")
    stock__lt = filters.NumberFilter(field_name="stock", lookup_expr="lt")

    # Convenient boolean: in_stock=true => stock > 0
    in_stock = filters.BooleanFilter(method="filter_in_stock")

    class Meta:
        model = Product
        fields = [
            "name",
            "price__gte",
            "price__lte",
            "stock",
            "stock__gte",
            "stock__lte",
            "stock__lt",
            "in_stock",
        ]

    def filter_in_stock(self, queryset, name, value):
        """Return products with stock > 0 when value is True, else stock == 0."""
        if value is True:
            return queryset.filter(stock__gt=0)
        if value is False:
            return queryset.filter(stock__lte=0)
        return queryset


class OrderFilter(filters.FilterSet):
    """Filters for Order model: totals, date ranges, related lookups and ordering."""

    total_amount__gte = filters.NumberFilter(field_name="total_amount", lookup_expr="gte")
    total_amount__lte = filters.NumberFilter(field_name="total_amount", lookup_expr="lte")
    order_date__gte = filters.IsoDateTimeFilter(field_name="order_date", lookup_expr="gte")
    order_date__lte = filters.IsoDateTimeFilter(field_name="order_date", lookup_expr="lte")

    # Related lookups
    customer_name = filters.CharFilter(field_name="customer__name", lookup_expr="icontains")
    product_name = filters.CharFilter(field_name="products__name", lookup_expr="icontains")
    product_id = filters.NumberFilter(field_name="products__id", lookup_expr="exact")

    # Allow ordering results (use ?ordering=order_date or -total_amount)
    order_by = filters.OrderingFilter(
        fields=(("order_date", "order_date"), ("total_amount", "total_amount"))
    )

    class Meta:
        model = Order
        fields = [
            "total_amount__gte",
            "total_amount__lte",
            "order_date__gte",
            "order_date__lte",
            "customer_name",
            "product_name",
            "product_id",
            "order_by",
        ]

    @property
    def qs(self):
        """Ensure distinct results when joining M2M (products)."""
        return super().qs.distinct()
