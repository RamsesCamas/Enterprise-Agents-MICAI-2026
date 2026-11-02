"""Who is who.

In production this is your identity provider: each person gets short-lived,
per-server OAuth tokens (MCP Enterprise-Managed Authorization). Here it is a
table, so we can see every decision.
"""

PEOPLE = {
    "ana": {"id": "ana@acme", "name": "Ana · Finance", "roles": ["finance"], "regions": ["norte", "centro", "sur"]},
    "maria": {"id": "maria@acme", "name": "María · Finance approver", "roles": ["finance", "approver"],
              "regions": ["norte", "centro", "sur"]},
    "luis": {"id": "luis@acme", "name": "Luis · Operations", "roles": ["operations"],
             "regions": ["norte", "centro", "sur"]},
    "pedro": {"id": "pedro@acme", "name": "Pedro · Viewer, norte", "roles": ["viewer"], "regions": ["norte"]},
}

# The token each person's servers start with. The model never sees these.
TOKENS = {
    "token-ana": "ana",
    "token-maria": "maria",
    "token-luis": "luis",
    "token-pedro": "pedro",
}

# What each role may do without anyone else's approval
ALLOWED_EFFECTS = {
    "viewer": ["read"],
    "operations": ["read", "write"],
    "finance": ["read", "write", "irreversible"],
}


def person_for_token(token):
    if token not in TOKENS:
        raise SystemExit("Unknown credential")
    return PEOPLE[TOKENS[token]]


def token_for(person_name):
    for token, name in TOKENS.items():
        if name == person_name:
            return token
    raise KeyError(person_name)


def allowed_effects(person):
    allowed = set()
    for role in person["roles"]:
        allowed.update(ALLOWED_EFFECTS.get(role, []))
    return allowed
