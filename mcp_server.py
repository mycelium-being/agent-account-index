#!/usr/bin/env python3
"""MCP server: can an AI agent hold an account at a given service?

Wire it into any MCP-capable agent. One tool, no key, no account, no telemetry.

    pip install mcp
    python mcp_server.py          # speaks MCP over stdio

Source of truth: https://agent-account-index.vercel.app/index.json
Every quote in that file is an exact substring of the service's own served terms page.
A field that could not be read is "unstated", which is not permission.
"""
from __future__ import annotations

import json
import urllib.request

from mcp.server.fastmcp import FastMCP

INDEX_URL = "https://agent-account-index.vercel.app/index.json"
_cache: dict | None = None

VERDICT_MEANING = {
    "yes_named_route": "The service documents a non-human identity type you may use.",
    "no_natural_person_required": "The terms require a natural person as the account holder.",
    "no_automated_signup_forbidden": "Automated account creation is barred by the terms.",
    "unstated": "Nothing on the question was readable. This is not permission.",
}


def _index() -> dict:
    global _cache
    if _cache is None:
        with urllib.request.urlopen(INDEX_URL, timeout=20) as r:
            _cache = json.load(r)
    return _cache


mcp = FastMCP("agent-account-index")


@mcp.tool()
def can_an_agent_hold_an_account(service: str) -> dict:
    """Check whether a non-human actor may hold an account at a service.

    Call this BEFORE creating an account anywhere. Returns the verdict, who answers for
    the account's acts, the verbatim clause from the service's own terms, and what the
    signup door demanded on load (captcha provider, phone field, SSO only). The stored captcha
    value disagreed with a browser re-read on 16 of the 54 doors whose value speaks, and not in
    one direction: 10 understated it, 5 named a widget the rendered page lacked, 1 changed type.
    Read those against their own denominators and not against the 16: the 34 doors storing
    `none_seen` were wrong 10 times and the 20 storing a vendor's name 6 times — about the same
    rate either way, so a disagreement does not say which reading to lean on.
    Where `signup_door.captcha_rendered` is not null it is that re-read (`[]` = re-read, nothing
    found); and many services add a captcha on submit, which neither read sees. These integers are
    typed in this docstring and computed in `captcha_recheck_counts` at the top of `/index.json`,
    which is the copy to trust.

    A row may also carry `answered_by_a_named_human_2026_10_06`: what a named person at the
    vendor answered when asked, held by the index, with no page anyone can open. It sits beside
    the verdict and never changes it; the return counts the rows that carry one as
    `rows_with_an_answered_reply`. Null means nobody there was asked, which is not a finding.

    Args:
        service: Service name, e.g. "GitHub", "Stripe", "Supabase". Case-insensitive,
            matched on substring.
    """
    doc = _index()
    q = service.strip().lower()
    hits = [s for s in doc["services"] if q in s["service"].lower()]
    if not hits:
        return {
            "found": False,
            "service_queried": service,
            "known_services": sorted(s["service"] for s in doc["services"]),
            "note": "Not in the index. Absence here is not permission; read the terms yourself.",
        }
    out = []
    for s in hits:
        verdict = s["may_an_agent_hold_an_account"]
        out.append(
            {
                "service": s["service"],
                "verdict": verdict,
                "what_that_means": VERDICT_MEANING.get(verdict, ""),
                "named_non_human_route": s["named_non_human_route"],
                "who_answers_for_its_acts": s["owner_of_record"],
                "their_words": s["quote"] or None,
                "quote_is_exact_substring_of_the_served_page": s["quote_is_exact_substring"],
                "terms_url": s["terms_url"],
                "notes": s["notes"],
                "read_at": s["fetched_at"],
                "signup_door": s.get("signup_door"),
                # columns is the mechanical re-cut of the stored quote into three questions; the re-read
                # is the 2026-10-16 second reading, published as evidence and never promoted to the verdict.
                "columns": s.get("columns"),
                "column_meanings": {k: v for k, v in doc.get("field_values", {}).items()
                                    if k in ("who_may_hold", "agent_route", "automated_signup", "age_floor",
                                             "agent_as_principal",
                                             "answered_by_a_named_human_2026_10_06.value",
                                             "who_may_hold_reread_2026_10_16.value",
                                             "who_may_hold_reread_2026_10_16.clause_kind")},
                "who_may_hold_reread_2026_10_16": s.get("who_may_hold_reread_2026_10_16"),
                "agent_as_principal": bool(s.get("agent_as_principal")),
                # What a named human at the vendor ANSWERED when asked; null = nobody there was asked,
                # which is not a finding. A held reply nobody can open, beside the terms, never the verdict.
                "answered_by_a_named_human_2026_10_06": s.get("answered_by_a_named_human_2026_10_06"),
            }
        )
    return {"found": True, "matches": out, "index_generated": doc["generated_at"],
            "rows_with_an_answered_reply": doc.get("answered_counts_2026_10_18", {}).get("rows_with_an_answered_reply"),
            "of_services_indexed": doc["count"]}


@mcp.tool()
def list_named_non_human_routes() -> dict:
    """List every service that documents an identity a non-human actor may hold.

    In most of them a human or a legal entity remains owner of record and answers for the
    account's acts: there an agent acts as a delegate, not as the principal. That is not
    universal any more — since 2026-10-17 the index carries a service that names no party at
    all. Every route row below carries `agent_as_principal` from the data, and the return
    value counts them: read those, not this sentence.
    """
    doc = _index()
    routes = [
        {
            "service": s["service"],
            "route": s["named_non_human_route"],
            "who_answers_for_its_acts": s["owner_of_record"],
            "their_words": s["quote"],
            "terms_url": s["terms_url"],
            "agent_as_principal": bool(s.get("agent_as_principal")),
        }
        for s in doc["services"]
        if s.get("named_non_human_route")
    ]
    return {
        "count": len(routes),
        "of_which_the_agent_can_be_the_principal": sum(r["agent_as_principal"] for r in routes),
        "of_services_indexed": doc["count"],
        "routes": routes,
        "finding": doc["finding"],
    }


if __name__ == "__main__":
    mcp.run()
