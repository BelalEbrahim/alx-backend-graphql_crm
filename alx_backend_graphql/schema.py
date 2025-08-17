"""
Top-level GraphQL schema that composes the CRM app's Query/Mutation types
and exposes a small example field `hello`.
"""
from typing import Optional

import graphene
from crm.schema import Query as CRMQuery, Mutation as CRMMutation


class Query(CRMQuery, graphene.ObjectType):
    """
    Root query type composed with the CRMQuery.
    Adds a simple 'hello' field for testing or quick health checks.
    """

    hello = graphene.String(
        name=graphene.Argument(graphene.String, default_value=None),
        description="A friendly greeting. Optionally pass `name` to personalize.",
    )

    def resolve_hello(self, info, name: Optional[str] = None) -> str:
        if name:
            return f"Hello, {name}!"
        return "Hello, GraphQL!"


class Mutation(CRMMutation, graphene.ObjectType):
    """Root mutation type composed with the CRMMutation (if any)."""
    pass


# Create schema. auto_camelcase=False keeps field names exactly as written (no camelCasing).
schema = graphene.Schema(query=Query, mutation=Mutation, auto_camelcase=False)

__all__ = ("schema",)
