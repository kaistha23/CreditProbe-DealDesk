# Round H · the local-demo tenant resolution fix

A candidate on top of the frozen Round H checkpoint
`245c50e45786c6e0c866b281f9dd74da17d160b5`. One adapter corrected, one
regression suite added. No dataset was regenerated, no release was
republished, no release id or fingerprint moved, and the frozen worktree was
not touched.

## What was observed

Both books are published and healthy, and both manifests name the same single
tenant:

| book | release | tenants |
|---|---|---|
| Corporate | `v4-saudi-corporate-20q-v4` | `["demo-tenant"]` |
| Retail | `v4-saudi-retail-20m-v5` | `["demo-tenant"]` |

The running Round H instance nevertheless refused every data route:

```
GET /api/v1/cockpit-v4/session          -> 200  {"tenant": "demo"}
GET /api/v1/cockpit-v4/attention?domain=corporate -> 403 SECURITY_DENIED
GET /api/v1/cockpit-v4/ecl?domain=corporate       -> 403 SECURITY_DENIED
GET /api/v1/cockpit-v4/schema?domain=corporate    -> 403 SECURITY_DENIED
GET /api/v1/cockpit-v4/attention?domain=retail    -> 403 SECURITY_DENIED
GET /api/v1/cockpit-v4/ecl?domain=retail          -> 403 SECURITY_DENIED
GET /api/v1/cockpit-v4/schema?domain=retail       -> 403 SECURITY_DENIED
```

with, for each book, its own correct release named in the refusal:

> Release 'v4-saudi-corporate-20q-v4' holds no data for tenant 'demo'. This is
> an access or configuration mismatch, not an empty portfolio.

The refusal was accurate. `demo_tenant` had resolved the tenant to `"demo"`,
and `"demo"` owns no rows in either book.

## Why it resolved to `demo`

`demo_tenant(runtime, cfg)` reads `runtime.release_summary["tenants"]` and
falls back when there is none. The fallback was `DEMO_PRINCIPAL["tenant"]`,
the literal `"demo"` — a value no published book has ever contained.

The fallback is not an edge case on this deployment: it is the path taken
whenever `build_runtime` does not complete, because `app.py` installs no
stand-in runtime and passes `None`. On the frozen Round H instance preflight
stops at `CAPABILITY_UNVERIFIED` (the stored credential returns HTTP 401), so
`runtime` is `None`, so the fallback decides the tenant for the whole landing
page. The dashboards themselves never needed the runtime — they read their
book through `domain_resolver` — so they were ready to answer and were denied
on the principal alone.

## The correction

`backend/cockpit_v4/app.py` only:

- `demo_tenant` falls back to `lake.DEFAULT_TENANT` (`"demo-tenant"`), the
  tenant the V4 lake publishes into, instead of the `"demo"` literal.
- `DEMO_PRINCIPAL["tenant"]` is seeded from the same constant, so no second
  tenant literal is left in the module to drift from the lake.
- Manifest-first behaviour is unchanged: a runtime that carries a
  `release_summary` with a non-empty `tenants` list still wins, and still
  returns `tenants[0]` exactly as before.

Nothing else was touched: not the analytical engine, orchestration, query
validation or repair, the datasets, the manifests, release ids or
fingerprints, the attention or dashboard calculations, model or provider
configuration, the ports, or the launcher.

## Live result over the same published books

```
SESSION tenant='demo-tenant' profile='Local UAT'

CORPORATE  release v4-saudi-corporate-20q-v4  fp c79d0fdf8753576f
  ATTENTION 200 · 2026Q2 vs 2026Q1 · SAR million · 5 segments, 4 highlights
    Construction: ECL rose to SAR 275,512 million
    Supply Chain Finance: ECL rose to SAR 89,901 million
    Makkah: ECL rose to SAR 183,510 million
  ECL       200 · profile + decomposition present
  BROWSE    200 · 4 relations (corp_borrower/facility/collateral/covenant_quarter)

RETAIL     release v4-saudi-retail-20m-v5     fp c23a15d78ba88d39
  ATTENTION 200 · 2026-08 vs 2026-07 · SAR million · 5 segments, 4 highlights
    Mortgage: ECL rose to SAR 45 million
    Affluent: ECL rose to SAR 56 million
    Madinah: Delinquency rose to 2.97%
  ECL       200 · profile + decomposition present
  BROWSE    200 · 4 relations (retail_customer/account/behaviour/collateral_month)
```

Each book answers from its own release, at its own frequency, with its own
fingerprint. Neither is substituted for the other.

## Regression coverage

`tests/cockpit_v4/test_demo_tenant_resolution.py` — evidence label **UNIT**.

| | claim |
|---|---|
| A | `tenants=["some-tenant"]` resolves to `"some-tenant"`; the real pinned release resolves to its own manifest tenant |
| B | no `release_summary` at all (and `runtime is None`) resolves to `lake.DEFAULT_TENANT`, and never to `"demo"` |
| C | an empty `tenants` list (`[]`, `()`, `None`, absent key) resolves to `lake.DEFAULT_TENANT` |
| D | the loopback resolver hands that tenant to the principal on all four loopback hosts, and the rest of the demo principal is unchanged |
| E | off-host callers still get nothing, `local_demo_auth=False` still issues nothing, and a request header still cannot name a tenant |

Proved by a control run with the fix reverted and everything else identical:
B, C and D fail, A and E pass. A and E are guards on behaviour this change
must not alter, so passing in both directions is the correct result for them.
