import graphene


class Query(graphene.ObjectType):
    hello = graphene.String(description="A friendly greeting")

    def resolve_hello(root, info):
        return "Hello, GraphQL!"


schema = graphene.Schema(query=Query)
