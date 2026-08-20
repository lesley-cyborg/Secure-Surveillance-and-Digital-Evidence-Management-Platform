# API Contract

## Contract source

Primary contract:

`documentation/api/openapi.yaml`

Reported contract facts:

- OpenAPI 3.1.2
- 39 paths
- 48 operations
- 70 schemas
- 11 response components
- 15 parameter components
- bearer security scheme
- RBAC metadata on every operation
- audit metadata on every operation
- sensitive writes require idempotency keys

## Contract tags

The documented operation distribution is:

- Authentication: 5
- Users: 8
- Cameras: 6
- Incidents: 9
- Evidence: 7
- Chain of Custody: 5
- Reports: 4
- Notifications: 2
- Audit: 2

## Implementation warning

The OpenAPI contract is ahead of some router implementations.

For example, the current custody router is only:

```python
APIRouter(prefix="/custody", tags=["Custody"])
```

Therefore an AI must not claim the five documented custody operations are implemented merely because they exist in OpenAPI.

Before implementing an endpoint:
1. inspect the OpenAPI operation
2. inspect current service/repository code
3. inspect security dependencies
4. inspect tests
5. preserve idempotency/audit requirements

## Public contract stability

AI-engine Phase 5 documentation explicitly requires public detection schemas/contracts to remain stable while production model adapters evolve.
