# MCP-001 Step 02 Anime Tool Mapping

## Files

- Modify `backend/app/mcp_server/__init__.py`.
- Consume descriptors from `backend/app/capabilities/anime.py`.
- Test in `backend/tests/mcp/test_server.py`.

## Requirements

Build tool definitions from AnimeCapability action descriptors rather than
maintaining a second hand-written schema. Preserve these public tool names:

- `anime_search`
- `anime_get_detail`
- `anime_get_staff`
- `anime_get_cast`
- `anime_get_reviews`

Route calls back through `AnimeCapability.execute()` so validation, data access,
and typed result handling remain owned by the capability layer.

## Acceptance

- tools/list returns exactly the five Anime tools above.
- Names, descriptions, required fields, and input schemas come from capability
  metadata.
- Known calls are dispatched to the matching Anime action.
- Unknown tool names return a structured failure and never fall through to an
  arbitrary capability method.
