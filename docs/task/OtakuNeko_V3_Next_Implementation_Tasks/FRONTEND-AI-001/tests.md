# FRONTEND-AI-001 Tests

## Required Coverage

- Typed query serialization, authenticated requests, errors, and `204` bodies.
- Sidebar active state, workspace section routing, keyboard use, and layout.
- Trace filters, cursor reset, event ordering, redaction display, cancellation,
  stale responses, empty states, and detail `404`.
- Proactive preview, timezone display, task mutations, confirmation, duplicate
  request prevention, and run history.
- Provider settings regression and API-key secrecy.
- Memory kind/all deletion confirmation and result counts.
- Responsive layouts and accessible names for controls and status regions.

## Verification Commands

```bash
cd frontend
pnpm test
pnpm typecheck
pnpm lint
pnpm build
```

Run the relevant authenticated backend API tests as a contract gate:

```bash
cd backend
uv run pytest tests/trace tests/proactive tests/memory/test_api.py -q
```

## Exit Gate

Use representative secrets in mocked provider and trace payloads and prove
that they do not appear in rendered output, URLs, console calls, snapshots, or
persisted workspace state. No acceptance test may depend on a live model
provider, scheduler clock, or another user's records.
