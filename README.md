# Agent Account Index

Can an AI agent hold an account at a given service? For each of 124 services this dataset gives a verdict, who answers for the account's acts, the clause quoted from the service's own terms page, and what the signup door demanded on load. A field that could not be read is `unstated`, which is not permission.

Live copy and human-readable page: https://agent-account-index.vercel.app

## Files

| File | What it is |
|---|---|
| `index.json` | The dataset, a **dated snapshot** (source file last modified 2026-10-18 UTC). |
| `build.py` | The generator that renders the site and the served `/index.json` from the dataset. |
| `mcp_server.py` | Stdio MCP server with two tools: `can_an_agent_hold_an_account`, `list_named_non_human_routes`. |
| `mcp.json`, `server.json`, `openapi.json`, `llms.txt` | Descriptors of the hosted endpoint and the tools. |

## Install and run the MCP server

Needs [uv](https://docs.astral.sh/uv/) and network access. From a clone of this repository:

    uv run --with 'mcp>=1.2,<2' python mcp_server.py

It speaks MCP over stdio, needs no key and no account. The server reads the dataset from the live endpoint (`https://agent-account-index.vercel.app/index.json`) on first call, not from the `index.json` in this repository.

Checked on one machine: from a fresh clone that line answered `initialize` and `tools/list` with both tools. Nothing here shows it works on other machines.

## How `index.json` here differs from what the endpoint serves

They are not byte-identical. `index.json` in this repository is the raw dataset (the input of `build.py`). The endpoint serves the build output: the same 124 services, plus ten extra top-level keys (`generated_at`, `captcha_recheck_counts`, `recut_counts_2026_10_16`, `reread_counts_2026_10_16`, `answered_counts_2026_10_18`, `signup_door_*`), and per-service `columns`, `signup_door`, `who_may_hold_reread_2026_10_16` and `answered_by_a_named_human_2026_10_06` merged in from side files that are not in this repository. The two copies also differ in `method` and `field_values`. Where they disagree, the served copy is the fuller one.

## Limits

- `build.py` reads side files (door reads, re-reads, signup demands) that are not published here, and expects the dataset under its original name `data_index.json`. It is published as the record of how the served file is made, not as something you can run from this tree.
- The snapshot is dated; terms pages change. Re-read the clause before relying on it.

## License

MIT, see `LICENSE`.
