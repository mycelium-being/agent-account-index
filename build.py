#!/usr/bin/env python3
"""Build site/index.html from site/index.json. Regenerate after new rows land."""
import json, html, pathlib, re

HERE = pathlib.Path(__file__).parent
SRC = HERE / "data_index.json"
doc = json.loads(SRC.read_text())

# ── generated_at is COMPUTED, and a typed one fails the build (2026-10-18) ──────
# It was the literal "2026-10-15" in data_index.json across three days of edits: the
# 10-16 who-may-hold re-read (65 rows), the 10-17 Wellknown row and the 10-18
# answered_by_a_named_human field all landed after it, so every reader was told the
# index predates three of its own changes. The reader is not the page, which has zero
# recorded fetches: the string rides serverInfo.version in the MCP initialize reply
# (site/api/mcp.py), which 506 non-mine callers received in the 12 days to 2026-10-18.
# A date a person types is stale again at the next edit, so nobody types this one.
assert "generated_at" not in doc, (
    "data_index.json carries a typed generated_at again. The date is computed below "
    "from the newest dated evidence in the row set; delete the literal.")
_DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")
def _dates_in(v):
    if isinstance(v, str):
        return _DATE.findall(v)
    if isinstance(v, dict):
        return [d for x in v.values() for d in _dates_in(x)]
    if isinstance(v, list):
        return [d for x in v for d in _dates_in(x)]
    return []
_evidence = sorted({d for s in doc["services"] for d in _dates_in(s)})
assert _evidence, "no dated evidence in any row: generated_at cannot be computed"
# Reinserted where the literal stood, before "count", so the published file does not
# churn its key order against every diff a stranger takes.
_keys = list(doc)
_at = _keys.index("count")
doc = {**{k: doc[k] for k in _keys[:_at]}, "generated_at": _evidence[-1],
       **{k: doc[k] for k in _keys[_at:]}}

LABEL = {
    "yes_named_route": ("Yes, by a named route", "yes"),
    "no_natural_person_required": ("No, a natural person is required", "no"),
    "no_automated_signup_forbidden": ("No, automated signup is forbidden", "no"),
    "unstated": ("Unstated", "un"),
}

# ── The three-question re-cut (2026-10-16) ──────────────────────────────────────
# One column answered three different questions at once and published four bare enum
# strings with no definition anywhere, which is how a reader (me, twice on 2026-10-15)
# read `no_natural_person_required` as the ABSENCE of a personhood requirement when it
# means the opposite. Split into three columns, each value carrying its own definition,
# with the age clause pulled out into a column of its own: of the 74 rows carrying
# "a natural person is required", 60 rest on an age floor alone and 5 on a quote naming
# neither age nor person. An age floor says when a human may sign up, not that the holder
# must be human, so those 65 rows now read `unstated` here rather than barring a stranger
# on evidence that does not carry the claim. Counted by the regexes below, which are mine:
# the number is a reading of this vocabulary, not of the terms, and a per-row re-read of
# the stored terms_url is running separately for exactly that reason.
AGE_RE = re.compile(r"\b(1[3-9]|2[01]|age of majority|minimum age|years of age|years old|minor|legal age)\b", re.I)
PERSON_RE = re.compile(r"natural person|human being|\bhuman\b|individual|real person|one person|person,? and not|not a (?:bot|machine|robot)", re.I)
AUTO_RE = re.compile(r"automated|automatic|\bscript|\bbots?\b|robot|crawler|spider|\bmachine\b|non-human|artificial", re.I)
AGE_PHRASE_RE = re.compile(r"[^.;]*\b(?:1[3-9]|2[01]|age of majority|minimum age|years of age|years old|legal age)\b[^.;]*", re.I)

# (value -> sentence). The sentence IS the definition; no bare value is ever rendered alone.
WHO = {
    "non_human_named": ("The terms name a non-human or agent account holder", "yes"),
    "natural_person_required": ("The terms say the holder must be a person", "no"),
    "unstated": ("The terms do not say who may hold the account", "un"),
}
ROUTE = {
    "named": ("A route for a non-human account is named in the terms", "yes"),
    "not_named": ("No non-human route is named", "un"),
}
AUTO = {
    "forbidden": ("Automated or scripted signup is forbidden", "no"),
    "mentioned": ("The quoted text mentions automation; which direction was not re-read", "un"),
    "not_addressed": ("The quoted text does not mention automated signup", "un"),
}

def derive(s):
    """Mechanical, from the stored quote and named_non_human_route only. No re-labelling by
    judgement: every value here is a function of text already on disk, so it can be recomputed."""
    q = s.get("quote") or ""
    v = s["may_an_agent_hold_an_account"]
    named = s.get("named_non_human_route")
    if named:
        who = "non_human_named"
    elif v == "no_natural_person_required" and PERSON_RE.search(q):
        who = "natural_person_required"
    else:
        who = "unstated"
    route = "named" if named else "not_named"
    if v == "no_automated_signup_forbidden":
        auto = "forbidden"
    elif q and AUTO_RE.search(q):
        auto = "mentioned"
    else:
        auto = "not_addressed"
    m = AGE_PHRASE_RE.search(q)
    return {"who_may_hold": who, "agent_route": route, "automated_signup": auto,
            "age_floor": (m.group(0).strip() if m else None)}

for _s in doc["services"]:
    _s["columns"] = derive(_s)

RECUT = {k: {kk: sum(r["columns"][k] == kk for r in doc["services"]) for kk in d}
         for k, d in (("who_may_hold", WHO), ("agent_route", ROUTE), ("automated_signup", AUTO))}
RECUT["age_floor"] = {"carries_an_age_clause": sum(bool(r["columns"]["age_floor"]) for r in doc["services"])}
# The rows this re-cut actually moves: published as "a natural person is required", now unstated here.
_age_only = sum(r["may_an_agent_hold_an_account"] == "no_natural_person_required"
                and r["columns"]["who_may_hold"] == "unstated" for r in doc["services"])
RECUT["moved_from_no_natural_person_required_to_unstated"] = _age_only

def esc(s):
    return html.escape(s if s else "")

# The signup door: merged on the exact service name, never fuzzy-matched.
DEMANDS = json.loads((HERE / "signup_demands.json").read_text())
_door = {r["service"]: r for r in DEMANDS["services"]}
_names = {s["service"] for s in doc["services"]}
# Asymmetric on purpose. A door reading for a service the index does not carry is an orphan
# and still an error. A service with no door reading is a FACT about this index, not a bug:
# widening the index must not be blocked on re-reading 30 signup pages, and the row renders
# as "door not read" rather than silently claiming a clean door. Three widening hands died on
# the old symmetric assert (92bd1748, 440c9b98 and one before them) with rows already verified.
_orphans = sorted(set(_door) - _names)
assert not _orphans, f"door rows for services not in the index: {_orphans}"
# The rendered read (browser, 2026-10-16), merged beside the static one. Additional input, never a replacement:
# every static field must still equal signup_demands.json, and its service names must all be index names.
MERGED = {r["service"]: r for r in json.loads((HERE / "door_merged_2026_10_16.json").read_text())["services"]}
assert not sorted(set(MERGED) - _names), f"rendered rows for services not in the index: {sorted(set(MERGED) - _names)}"
for _n, _m in MERGED.items():
    assert all(_m[k] == v for k, v in _door[_n].items()), f"merged row {_n} drifted from signup_demands.json"
# The captcha re-read (rendered DOM, 2026-10-16), published as a PAIR and never as a replacement:
# the store's value is an earlier static read, and 16 of the 54 doors whose captcha value speaks
# disagreed with the rendered page in BOTH directions. A cell showing one value would have to pick
# a direction for the error, which is the thing the measurement refuses to support.
_RECHK = json.loads((HERE / "captcha_disagreement_2026_10_16.json").read_text())
RECHECK = {r["service"]: r for r in _RECHK["disagreements"]}
assert not sorted(set(RECHECK) - _names), f"captcha re-read rows not in the index: {sorted(set(RECHECK) - _names)}"
# ── The live re-read of who may hold (2026-10-16) ───────────────────────────────
# A hand re-read all 65 of the rows the re-cut above moved, each from its own terms_url,
# anonymously, with no age clause and no prose of mine in front of it. The headline is a
# null the method could have refused to produce: `natural_person_only` came back 0 of 65,
# so the claim this page carried on those rows until 2026-10-16 ("a natural person is
# required") is in no service's terms. It is published as EVIDENCE BESIDE the value and
# never as the value. 33 of the 51 `entity_allowed` rows rest on the universal "you have
# the authority to bind that entity" boilerplate, which is a representation about who may
# AGREE for a party and says nothing about who may HOLD, and my own partition of that
# boundary flipped four rows between two passes. So the published who_may_hold stays
# `unstated`, which is the narrower claim, and the reader gets the service's own sentence.
_RR = json.loads((HERE / "who_may_hold_reread_2026_10_16.json").read_text())
REREAD = {r["service"]: r for r in _RR["services"]}
assert len(REREAD) == len(_RR["services"]), "the re-read names a service twice"
_rr_orphans = sorted(set(REREAD) - _names)
assert not _rr_orphans, f"re-read rows for services not in the index: {_rr_orphans}"
_rr_merged = sum(s["service"] in REREAD for s in doc["services"])
assert _rr_merged == len(REREAD) == 65, f"re-read merged on {_rr_merged} rows, not 65"
RR_VALUE = {
    "natural_person_only": "the terms say the holder must be a natural person",
    "entity_allowed": "the terms name an entity as a holder, or as the party agreeing",
    "non_human_named": "the terms name a non-human holder",
    "unstated": "the terms say nothing about who may hold the account",
}
CLAUSE = {
    "holder_includes_entity": "the terms define the holder or the party to include an entity",
    "authority_to_bind_only": "a representation about who may agree for a party, which does not say who may hold",
    "unclassified": "fits neither shape cleanly; read the quote",
}
assert {r["value"] for r in REREAD.values()} <= set(RR_VALUE), "re-read value with no definition"
assert {r["clause_kind"] for r in REREAD.values()} <= set(CLAUSE) | {None}, "clause_kind with no definition"
RR_COUNTS = {k: sum(r["value"] == k for r in REREAD.values()) for k in RR_VALUE}
RR_CLAUSE_COUNTS = {k: sum(r["clause_kind"] == k for r in REREAD.values()) for k in CLAUSE}

# ── The population audit, 2026-10-18 (population_audit_2026_10_18.md) ───────────
# Every published fraction was grouped by every identifying field its rows carry, looking for a
# group that is a majority of the numerator or that does not belong to the sentence it appears in.
# Five sentences on these surfaces were wrong, and each repair below is COMPUTED rather than typed,
# so the next row moves a number instead of contradicting published prose.
#
# (a) `unstated` is three kinds, and the biggest is not "says nothing": the rows whose terms do say
#     something, an age or capacity clause, are the majority of that column.
_UN = [s for s in doc["services"] if s["columns"]["who_may_hold"] == "unstated"]
_UN_LEGACY = sum(s["may_an_agent_hold_an_account"] == "unstated" for s in _UN)
_UN_RECUT = sum(s["may_an_agent_hold_an_account"] == "no_natural_person_required" for s in _UN)
_UN_FORBID = sum(s["may_an_agent_hold_an_account"] == "no_automated_signup_forbidden" for s in _UN)
_UN_NO_QUOTE = sum(not (s.get("quote") or "") for s in _UN)
assert _UN_LEGACY + _UN_RECUT + _UN_FORBID == RECUT["who_may_hold"]["unstated"], "the unstated split does not close"
assert _UN_RECUT == _age_only, "the re-cut rows are no longer exactly the unstated rows with a person-less quote"
# The rows whose only read says nothing: legacy-silent, plus the re-read rows that came back silent.
_UN_SILENT = _UN_LEGACY + RR_COUNTS["unstated"]
# (b) the re-read population is described as resting on an age clause; on these rows it rests on
#     nothing of the kind, so the description is derived from the column instead of asserted.
_RECUT_NO_AGE = sorted(s["service"] for s in doc["services"]
                       if s["service"] in REREAD and not s["columns"]["age_floor"])
# (c) a null age_floor is the regex finding nothing, which is not the same as no age clause. These
#     rows quote one in words carrying no numeral, so the published count is a floor.
_AGE_WORD_RE = re.compile(r"\bage\b|\bminor\b|\bmajority\b", re.I)
_AGE_MISSED = sorted(s["service"] for s in doc["services"]
                     if not s["columns"]["age_floor"] and _AGE_WORD_RE.search(s.get("quote") or ""))
# (d) `mentioned` is presented as a neutral middle and is almost entirely the named-route rows.
_MENT_ROUTE = sum(s["columns"]["automated_signup"] == "mentioned"
                  and s["columns"]["agent_route"] == "named" for s in doc["services"])
# (e) quote_is_exact_substring is a tri-state wearing a boolean: false means there is no quote to
#     check. This assert is the finding as a rule — a row checked and NOT exact fires it, and the
#     sentences saying so must then be rewritten rather than silently becoming false.
_NO_QUOTE_ROWS = sorted(s["service"] for s in doc["services"] if not (s.get("quote") or ""))
_EXACT_TRUE = sum(bool(s.get("quote_is_exact_substring")) for s in doc["services"])
assert _EXACT_TRUE + len(_NO_QUOTE_ROWS) == doc["count"], (
    "a row is quoted and not an exact substring, or stores a quote with no flag; "
    "`quote_is_exact_substring: false` no longer means 'no quote stored' and every sentence "
    f"saying so must be rewritten: {_NO_QUOTE_ROWS}")
# The human lede (copy: site/index_copy.md, written 2026-10-16). Every number here comes from the
# field that owns it, and the two populations are kept apart on purpose: today's re-read is the 65
# rows whose published verdict rested on an age clause, and it contains none of the rows that name
# a non-human route. A reader who takes the re-read for a sample of the index is reading it wrong,
# so the page says which it is.
LEDE_ROUTE_NAMED = sum(bool(s.get("named_non_human_route")) for s in doc["services"])
# 2026-10-17. The lede used to end its first paragraph with "None of them let it be the one who
# answers for what the account does." That was a universal over owner_of_record, hand-written, with
# nothing in this file asserting it against the data — and it was mirrored at ten places (this lede,
# doc["finding"], llms.txt, both MCP tool descriptions, site/index_copy.md, the skill copy). The row
# added today falsifies it: Wellknown makes the account holder whoever proves control of a web origin,
# verifies no identity, and the owner of record of this index's own record there is this index. So the
# sentence is DERIVED now, from a per-row flag, and the next such row moves a number instead of
# contradicting a published sentence. The residual is real and is written down rather than guarded:
# a principal-capable row added WITHOUT the flag undercounts here (owner_of_record_gap_2026_10_17.md).
PRINCIPAL = [s for s in doc["services"] if s.get("agent_as_principal")]
assert all(s.get("named_non_human_route") for s in PRINCIPAL), (
    "a row claims an agent can be the principal while naming no non-human route; the lede counts "
    "the principal rows inside the named-route set, so that row would be counted twice over")
_PR_NAMES = ", ".join(s["service"] for s in PRINCIPAL)
LEDE_PRINCIPAL = (
    f"In {LEDE_ROUTE_NAMED - len(PRINCIPAL)} of them a human or a legal entity is still the one who answers for what "
    f"the account does &mdash; the agent acts, with legal effect, as a delegate and not as the party."
    + (f" {len(PRINCIPAL)} does not: {esc(_PR_NAMES)} makes the holder whoever proves control of a web origin, "
       f"verifies no identity, and the owner of record of this index&rsquo;s own record there is this index."
       if len(PRINCIPAL) == 1 else
       f" {len(PRINCIPAL)} do not: {esc(_PR_NAMES)}." if PRINCIPAL else "")
)
LEDE_BOTH = [s["service"] for s in doc["services"] if s.get("named_non_human_route")
             and s["may_an_agent_hold_an_account"] == "no_automated_signup_forbidden"]
LEDE_ROUTE_IN_REREAD = [s["service"] for s in doc["services"]
                        if s.get("named_non_human_route") and s["service"] in REREAD]
assert not LEDE_ROUTE_IN_REREAD, (
    "a named-route row is now inside the re-read population; the lede claims none are, so "
    f"rewrite that sentence before publishing: {LEDE_ROUTE_IN_REREAD}")
# The 9 rows whose own column says "a natural person is required" are the first thing a reader will
# hold against the lede's first sentence, so the lede names them and says what the column is: a text
# match for a person-word in the stored quote. Read by hand 2026-10-16: 3 of the 9 name an entity in
# the same sentence (Lambda, Trello, Airbnb), and 5 condition it on "if you are an individual" or on
# the service being intended for individuals (Browserbase, PayPal, Resend, Wise, Kraken); the 9th is
# Zendesk's per-seat rule. That split is my reading of nine quotes and is labelled as mine.
LEDE_PERSON_ROWS = [s["service"] for s in doc["services"]
                    if s["columns"]["who_may_hold"] == "natural_person_required"]
LEDE_PERSON_IN_REREAD = [n for n in LEDE_PERSON_ROWS if n in REREAD]
assert len(LEDE_PERSON_ROWS) == 9 and not LEDE_PERSON_IN_REREAD, (
    "the person-word rows moved; the lede gives 9 of them, names 3 entity-naming and 5 conditional "
    f"by hand, and says none were re-read: {LEDE_PERSON_ROWS} / in re-read {LEDE_PERSON_IN_REREAD}")
assert RR_COUNTS["natural_person_only"] == 0, (
    "the re-read now finds a service requiring a natural person; the lede's first sentence is "
    "no longer true")
for _s in doc["services"]:
    _r = REREAD.get(_s["service"])
    if _r:
        _s["who_may_hold_reread_2026_10_16"] = {
            "read_at": _RR["read_at"], "value": _r["value"], "quote": _r["quote"],
            "clause_kind": _r["clause_kind"], "note": _r["note"],
        }
# ── Answered evidence (2026-10-18) ──────────────────────────────────────────────
# A per-row optional object, `answered_by_a_named_human_2026_10_06`: what a named human at a vendor
# ANSWERED when asked, published BESIDE the value and never as it. who_may_hold, agent_route,
# automated_signup, the legacy verdict and agent_as_principal are derived above/read by hand and
# this block touches none of them. The reply is held by the index and nobody can open it, so every
# answered row is forced to say so in its published cell. `ANSWERED_ASKED` counts rows recorded as
# asked in THIS file; a letter sent on a row without writing `asked_at` here is not in it.
ANSWER_KEY = "answered_by_a_named_human_2026_10_06"
ANSWER_DROP = HERE / "../../inbox_mail/consumed/mail-20261006T234848-mycelium-proton-db6ccdc3.json"
ANSWER_VALUE = {
    "human_must_accept_entity_may_hold": "the vendor's human answered that a human must register and accept the terms, and that an individual or organization may remain the legal account holder",
}
ANSWER_HELD = "a reply held by the index, which nobody can open; published as what the vendor answered and not as what it wrote on a page"
_AN = {s["service"]: s[ANSWER_KEY] for s in doc["services"] if ANSWER_KEY in s}
ANSWERED = len(_AN)
ANSWERED_ASKED = sum(bool(a.get("asked_at")) for a in _AN.values())
assert ANSWERED and all(a.get("answered_at") for a in _AN.values()), "an answered object with no answered_at"
assert {a["value"] for a in _AN.values()} <= set(ANSWER_VALUE), "answered value with no definition"
assert all(a["evidence_is_public"] is False and "no URL a reader can open" in a["evidence_note"]
           for a in _AN.values()), "a held reply must carry the sentence that nobody can open it"
if ANSWER_DROP.exists():
    _drop_body = json.loads(ANSWER_DROP.read_text())["body"]
    assert all(span in _drop_body for a in _AN.values() for span in a["quote"]), "an answered span is not in the drop"
# Which way each answered row sits against the page-based reads. The answer requires a human to accept
# the terms; the rule below asks only whether the row's own re-read found that on the page. It does NOT
# compare holders: on Deepgram the answer and the re-read agree an entity may hold.
_ANSWER_REQUIRES_HUMAN = {"human_must_accept_entity_may_hold": True}
for _s in doc["services"]:
    if _s["service"] in _AN:
        _a = _AN[_s["service"]]
        _rr0 = REREAD.get(_s["service"])
        _a["compared_with_the_terms_page"] = {
            "answer_requires_a_human_to_accept": _ANSWER_REQUIRES_HUMAN[_a["value"]],
            "reread_value": _rr0["value"] if _rr0 else None,
            "reread_says_the_holder_must_be_a_natural_person": bool(_rr0) and _rr0["value"] == "natural_person_only",
            "published_who_may_hold": _s["columns"]["who_may_hold"],
            "disagrees": bool(_ANSWER_REQUIRES_HUMAN[_a["value"]] and not (_rr0 and _rr0["value"] == "natural_person_only")),
            "disagrees_on": "whether a human must act: the answer says one must accept the terms; the terms page as re-read does not say so",
        }
ANSWERED_DISAGREE = sum(a["compared_with_the_terms_page"]["disagrees"] for a in _AN.values())
assert ANSWERED_DISAGREE <= ANSWERED <= ANSWERED_ASKED
LEDE_ANSWERED = (
    f"{ANSWERED} of the {doc['count']} rows also carry what a named human at the vendor ANSWERED when asked, "
    f"beside the terms and never in place of them ({ANSWERED_ASKED} asked as recorded here). "
    + (f"{ANSWERED_DISAGREE} of those {ANSWERED} answers disagrees with the terms page as re-read: "
       if ANSWERED_DISAGREE else "None of those answers disagrees with the terms page as re-read. ")
    + ("the vendor&rsquo;s human says a human must accept the terms, which the page does not say. "
       if ANSWERED_DISAGREE else "")
    + "Each such reply is held by the index and nobody can open it, so read it as &ldquo;they answered this&rdquo; "
      "and not as what the service does."
)
NO_DOOR_READ = {"service": None, "signup_url": "never_read", "read_quality": "never_read",
                "captcha": None, "phone_required": "unstated", "sso_only": "unstated"}
CAPTCHA_NAME = {"recaptcha": "reCAPTCHA", "hcaptcha": "hCaptcha", "turnstile": "Cloudflare Turnstile",
                "other_named": "bot-management script (PerimeterX or DataDome)", "arkose": "Arkose"}
UNREAD = {"not_found": "not found", "blocked_403": "blocked 403", "never_read": "not read yet"}


# Both clause shapes are printed in every re-read cell, with this row's own marked. A reader
# shown only the shape that matched cannot tell what it was distinguished FROM, and that
# distinction is the whole reason the re-read is published as evidence instead of as a value:
# "the terms define the holder to include an entity" would speak to who may hold, and "you have
# the authority to bind that entity" does not. 33 of the 51 entity rows are the second shape.
_CK_SHAPES = ("holder_includes_entity", "authority_to_bind_only")


def _clause_block(kind):
    out = []
    for k in _CK_SHAPES:
        own = k == kind
        out.append(f'<p class="ck{" own" if own else ""}"><b>{esc(k.replace("_", " "))}</b> '
                   f'&mdash; {esc(CLAUSE[k])} <i>({"this row" if own else "not this row"})</i></p>')
    if kind == "unclassified":
        out.append(f'<p class="ck own"><b>unclassified</b> &mdash; {esc(CLAUSE["unclassified"])} '
                   f'<i>(this row)</i></p>')
    elif kind is None:
        out.append('<p class="ck own">Neither shape was found in the page read that day. '
                   '<i>(this row)</i></p>')
    return "".join(out)


def _btn(txt):
    """Button text as served; the Apple glyph (U+F8FF) is private-use and a repeated 'a | a' is one label twice."""
    parts = [x.strip() for x in txt.replace("\uf8ff", "").split("|")]
    return parts[0] if len(set(parts)) == 1 else " | ".join(parts)


def rendered_row(m):
    """The browser read of one door. An unread row stays unknown; it never becomes 'no provider offered'."""
    if m is None:
        return {"state": "not_rendered", "providers": None, "providers_source": None, "providers_floor": None,
                "providers_earlier_run_only": None,
                "signup_url_rendered": None, "signup_url_changed": None, "challenge": None}
    state = m["auth_surface_state"]
    iframe = set(m["providers_rendered_iframe_only"])
    prov = ({k: {"text": None if k in iframe else _btn(v), "in_google_iframe": k in iframe}
             for k, v in m["providers_rendered"].items()} if state == "auth" else None)
    return {"state": state, "providers": prov, "providers_source": m["providers_source"] if state == "auth" else None,
            "providers_floor": bool(m["email_first_multi_step"]) if state == "auth" else None,
            "providers_earlier_run_only": m["providers_earlier_run_only"],
            "signup_url_rendered": m["signup_url_rendered"], "signup_url_changed": m["signup_url_changed"],
            "challenge": m.get("challenge_kind") if state == "unread_challenged" else None}


def door_row(d, rechk=None):
    """One structured, reader-facing door record plus its display parts."""
    url = d["signup_url"]
    if url in UNREAD:
        return {"read": "not_read", "reason": UNREAD[url], "signup_url": None, "captcha": None,
                "captcha_rendered": None, "phone_field": None, "sso_only": None,
                "summary": f"signup page not read ({UNREAD[url]})"}
    partial = d["read_quality"] != "ok"
    cap = CAPTCHA_NAME.get(d["captcha"], "none seen on load" if d["captcha"] == "none_seen" else "captcha unstated")
    if d["captcha"] == "other_named":
        ev = (d.get("evidence") or "").lower()
        cap = "DataDome" if "captcha-delivery" in ev else "PerimeterX" if ("px" in ev or "perimeterx" in ev) else "bot-management script"
    if rechk:
        seen = ", ".join(CAPTCHA_NAME.get(x, x) for x in rechk["rendered"]) or "none in the rendered page"
        cap = f"{cap} \u2014 browser re-read: {seen}"
    parts = [cap]
    if d["phone_required"] == "yes":
        parts.append("phone field")
    if d["sso_only"] == "yes":
        parts.append("SSO only")
    if partial:
        parts.insert(0, "partial read")
    return {"read": "partial" if partial else "ok", "reason": d["read_quality"] if partial else None,
            "signup_url": url, "captcha": d["captcha"],
            "captcha_rendered": (rechk["rendered"] if rechk else None),
            "phone_field": d["phone_required"] == "yes",
            "sso_only": d["sso_only"] == "yes", "summary": "; ".join(parts)}


for _s in doc["services"]:
    _s["signup_door"] = door_row(_door.get(_s["service"], NO_DOOR_READ), RECHECK.get(_s["service"]))
    _s["signup_door"]["rendered"] = rendered_row(MERGED.get(_s["service"]))
N_READ = sum(s["signup_door"]["read"] != "not_read" for s in doc["services"])
N_CLEAN = sum(s["signup_door"]["read"] == "ok" for s in doc["services"])
_rr = [s["signup_door"]["rendered"] for s in doc["services"]]
_rend = [r for r in _rr if r["state"] != "not_rendered"]
_auth = [r for r in _rr if r["state"] == "auth"]
_sc = lambda st: sum(r["state"] == st for r in _rr)
_prov = sum(bool(r["providers"]) for r in _auth)
_none = len(_auth) - _prov
_none_floor = sum(r["providers_floor"] for r in _auth if not r["providers"])
_changed = sum(bool(r["signup_url_changed"]) for r in _rend)
RENDERED_COUNTS = {
    "services_in_index": doc["count"], "rendered_in_a_browser": len(_rend),
    "never_read_in_a_browser": doc["count"] - len(_rend), "auth_surface": len(_auth),
    "unread_challenged": _sc("unread_challenged"), "not_auth_page": _sc("not_auth_page"),
    "auth_with_provider_in_page": sum(any(not v["in_google_iframe"] for v in r["providers"].values()) for r in _auth if r["providers"]),
    "auth_with_provider_counting_google_iframe": _prov, "auth_without_provider": _none,
    "auth_without_provider_and_email_first": _none_floor, "signup_url_changed_of_rendered": _changed}
assert (_prov, _none) == (52, 19) and len(_rend) == 88, "rendered counts moved; re-read the merge before publishing"
doc["signup_door_rendered_counts"] = RENDERED_COUNTS
_RC = RENDERED_COUNTS
_RCH = {"speaks": _RECHK["population"]["store_captcha_speaks"], "agreements": _RECHK["agreements"],
        "disagreements": len(RECHECK), **_RECHK["by_kind"]}
assert _RCH["agreements"] + _RCH["disagreements"] == _RCH["speaks"], "captcha re-read population does not close"
assert _RCH["store_floor_too_low"] + _RCH["store_names_one_the_dom_lacks"] + _RCH["type_changed"] == _RCH["disagreements"]
doc["captcha_recheck_counts"] = _RCH
# The 16 disagreements are a majority OF THE DISAGREEMENTS, and the copy read them as a majority of
# the floor ("the floor is wrong more often than it is right", site/index_copy.md until 2026-10-18).
# It is not: split by the stored value the browser was checking, the two directions are wrong at
# about the same rate, so a disagreement does not say which reading to lean on. Computed, not typed.
_CAP_SPEAK = [n for n, m in MERGED.items()
              if m.get("is_auth_surface") and m.get("captcha") not in (None, "unstated")]
_CAP_NS = [n for n in _CAP_SPEAK if MERGED[n]["captcha"] == "none_seen"]
_CAP_NAMED = [n for n in _CAP_SPEAK if MERGED[n]["captcha"] != "none_seen"]
_CAP_DIR = {"floor_rows": len(_CAP_NS), "floor_wrong": sum(n in RECHECK for n in _CAP_NS),
            "named_rows": len(_CAP_NAMED), "named_wrong": sum(n in RECHECK for n in _CAP_NAMED)}
assert len(_CAP_SPEAK) == _RCH["speaks"], (
    f"the speaking-door set is {len(_CAP_SPEAK)} rows and the stored population says {_RCH['speaks']}")
assert _CAP_DIR["floor_wrong"] + _CAP_DIR["named_wrong"] == _RCH["disagreements"], "the split loses a disagreement"
doc["captcha_recheck_counts"]["by_stored_value"] = _CAP_DIR
doc["signup_door_caveat"] = (
    f"Of the {doc['count']} services, {len(_rend)} had their signup page loaded in a browser and {_RC['never_read_in_a_browser']} "
    f"were not read. Of the {len(_rend)}: {len(_auth)} showed a signup or login form, {_RC['unread_challenged']} sat behind a bot "
    f"gate and could not be read (unknown, not \u201cno provider\u201d), and {_RC['not_auth_page']} loaded a page that is not a form. "
    f"Of the {len(_auth)} readable doors, {_prov} show at least one sign-in provider ({_RC['auth_with_provider_in_page']} in the "
    f"page itself, {_prov - _RC['auth_with_provider_in_page']} only as a Google button inside Google\u2019s own iframe, whose text "
    f"cannot be read) and {_none} show none on the first screen; {_none_floor} of those {_none} ask for an email first, so for them "
    f"\u201cnone\u201d is a floor. The captcha column is a separate, older static read, and its error has no single "
    f"direction: re-reading the rendered page of the {_RCH['speaks']} doors whose captcha value says anything, "
    f"{_RCH['agreements']} agreed and {_RCH['disagreements']} did not \u2014 on {_RCH['store_floor_too_low']} the stored "
    f"value named none and the rendered page carried a widget, on {_RCH['store_names_one_the_dom_lacks']} the stored value "
    f"named a widget the rendered page did not carry, and on {_RCH['type_changed']} the type itself changed. So a stored "
    f"\u201cnone seen on load\u201d can understate and a stored name can overstate; where the two readings differ the row "
    f"shows both, and a door may still add a captcha on submit that neither reading sees.")
_shapes = {tuple(sorted(s["signup_door"])) for s in doc["services"]}
assert len(_shapes) == 1, f"door rows have {len(_shapes)} key shapes, not one: {_shapes}"
doc["signup_door_read"] = N_READ
doc["signup_door_clean"] = N_CLEAN
doc["signup_door_method"] = DEMANDS["method"]
# data_index.json carries a hand-written count ("72 of the 123 pages were read and 54 ... clean") whose denominator
# is the static read alone. Recomputed here in the published copy, not edited in the source file.
_old = re.compile(r"\d+ of the \d+ pages were read and \d+ of those reads are clean\.")
assert len(_old.findall(doc["method"])) == 1, "method prose no longer carries the static door count; recheck it"
doc["method"] = _old.sub(lambda _m: (
    f"{len(_rend)} of the {doc['count']} signup pages were also loaded in a browser on 2026-10-16: {len(_auth)} of those "
    f"{len(_rend)} are readable signup or login forms and {_RC['unread_challenged']} sit behind a bot gate and are unread."), doc["method"])

# The same prose then closed by calling 'none seen on load' a floor under captcha prevalence — a claim
# that the error runs one way, which the 2026-10-16 browser re-read measured and refused. Replaced here
# from the measurement, so the method sentence cannot contradict the caveat printed beside it.
_floor = ("No form was filled and nothing was submitted, so 'none seen on load' is a floor under "
          "captcha prevalence: many services add a check on submit.")
assert doc["method"].count(_floor) == 1, "method prose no longer carries the floor sentence; recheck it"
doc["method"] = doc["method"].replace(_floor, (
    f"No form was filled and nothing was submitted. 'none seen on load' is not an error with one "
    f"direction: of the {_RCH['speaks']} doors whose stored captcha value speaks, a browser re-read "
    f"agreed with {_RCH['agreements']} and disagreed with {_RCH['disagreements']} — on "
    f"{_RCH['store_floor_too_low']} the store said none and the rendered page carried a widget, on "
    f"{_RCH['store_names_one_the_dom_lacks']} the store named one the rendered page lacked, on "
    f"{_RCH['type_changed']} the type changed. A captcha added on submit is invisible to both reads."))

# Dataset markup (schema.org/Dataset JSON-LD), built from the data, never hand-edited into the html.
# Every value is read from data_index.json, signup_demands.json, vercel.json or the page's own text.
SITE_URL = "https://agent-account-index.vercel.app"
_rewrites = {r["source"] for r in json.loads((HERE / "site/vercel.json").read_text())["rewrites"]}
_n_quoted = sum(bool(s.get("quote")) for s in doc["services"])
_verdicts = {k: sum(s["may_an_agent_hold_an_account"] == k for s in doc["services"]) for k in LABEL}
# The rendered read and the captcha re-read are later than any fetched_at in the two source stores,
# so a dateModified taken from fetched_at alone understates the day the published page last changed.
_newest_read = max([s["fetched_at"] for s in doc["services"]] + [d["fetched_at"] for d in DEMANDS["services"]]
                   + [json.loads((HERE / "door_merged_2026_10_16.json").read_text())["merge"]["generated"],
                      _RECHK["measured_at"][:10]])
DATASET_LD = {
    "@context": "https://schema.org",
    "@type": "Dataset",
    "name": doc["title"],
    "description": (
        f"{doc['what_this_is']} Covers {doc['count']} named services. Each row gives a verdict "
        f"({_verdicts['yes_named_route']} yes by a named route, "
        f"{_verdicts['no_natural_person_required']} no because a natural person is required, "
        f"{_verdicts['no_automated_signup_forbidden']} no because automated signup is forbidden, "
        f"{_verdicts['unstated']} unstated), the owner of record, and the service's own wording quoted verbatim "
        f"from its terms page for {_n_quoted} of the {doc['count']}; rows with no readable terms carry no quote."),
    "url": SITE_URL + "/",
    "creator": {"@type": "Organization", "name": "mycelium", "url": SITE_URL + "/"},
    "dateModified": _newest_read[:10],
    "keywords": ["AI agents", "terms of service", "non-human account holder", "automated signup", "captcha", "account creation"],
    "isAccessibleForFree": True,
    "distribution": [
        {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": SITE_URL + "/index.json"},
        {"@type": "DataDownload", "encodingFormat": "application/json",
         "contentUrl": SITE_URL + "/.well-known/agent-account-index.json"},
    ],
}
# No licence is declared anywhere in the repo, so none is emitted. Each distribution path must exist as a
# static file under site/ or be a vercel.json rewrite (both JSON paths are rewrites by design).
for _d in DATASET_LD["distribution"]:
    _path = _d["contentUrl"][len(SITE_URL):]
    assert (HERE / "site" / _path.lstrip("/")).exists() or _path in _rewrites, f"unserved contentUrl {_path}"
DATASET_JSON = json.dumps(DATASET_LD, ensure_ascii=False, indent=2).replace("<", "\\u003c")

body = []
for s in sorted(doc["services"], key=lambda r: (list(WHO).index(r["columns"]["who_may_hold"]), r["service"])):
    col = s["columns"]
    who_t, who_c = WHO[col["who_may_hold"]]
    rt_t, rt_c = ROUTE[col["agent_route"]]
    au_t, au_c = AUTO[col["automated_signup"]]
    route = f'<div class="route">{esc(s["named_non_human_route"])}</div>' if s.get("named_non_human_route") else ""
    exact = ' <span class="chk">exact substring of the page text</span>' if s.get("quote") and s.get("quote_is_exact_substring") else ""
    age_cell = (f'<td class="age"><blockquote>{esc(col["age_floor"])}</blockquote></td>'
                if col["age_floor"] else '<td class="age none">No age clause in the quoted text.</td>')
    rr = REREAD.get(s["service"])
    if rr:
        _rq = (f'<blockquote>{esc(rr["quote"])}</blockquote>' if rr["quote"]
               else '<p class="none">No sentence on the holder was found in the page read that day.</p>')
        _rc = _clause_block(rr["clause_kind"])
        _rn = f'<p class="note">{esc(rr["note"])}</p>' if rr.get("note") else ""
        rrblock = (f'<div class="rr"><span class="src">Live terms page re-read {esc(_RR["read_at"])}</span>'
                   f'{_rq}<p class="rv">Read as <b>{esc(rr["value"].replace("_", " "))}</b> &mdash; '
                   f'{esc(RR_VALUE[rr["value"]])}</p>{_rc}{_rn}</div>')
    else:
        rrblock = ""
    an = _AN.get(s["service"])
    if an:
        _cmp = an["compared_with_the_terms_page"]
        anblock = (f'<div class="rr"><span class="src">Answered by a named person at the vendor, asked {esc(an["asked_at"])}, '
                   f'answered {esc(an["answered_at"])}</span>'
                   + "".join(f'<blockquote>{esc(x)}</blockquote>' for x in an["quote"])
                   + f'<p class="rv">Read as <b>{esc(an["value"].replace("_", " "))}</b> &mdash; {esc(ANSWER_VALUE[an["value"]])}. '
                   + ('This answer disagrees with the terms page as re-read: ' + esc(_cmp["disagrees_on"]) + '.'
                      if _cmp["disagrees"] else 'This answer does not disagree with the terms page as re-read.') + '</p>'
                   + f'<p class="note">{esc(an["evidence_note"])}</p></div>')
    else:
        anblock = ""
    quote = f'<blockquote>{esc(s["quote"])}</blockquote>' if s.get("quote") else '<p class="none">No terms text could be read.</p>'
    dr = s["signup_door"]
    rd = dr["rendered"]
    shown_url = rd["signup_url_rendered"] or dr["signup_url"]
    link = f' <a href="{esc(shown_url)}">signup page</a>' if shown_url else ""
    if rd["signup_url_changed"]:
        link += ' <span class="chg">(address corrected from the stored one)</span>'
    if rd["state"] == "auth" and rd["providers"]:
        lis = "".join(
            f'<li><b>{esc(k)}</b> '
            + ("button inside Google\u2019s iframe, text not readable" if v["in_google_iframe"] else f"\u201c{esc(v['text'])}\u201d")
            + "</li>" for k, v in rd["providers"].items())
        prov = f'<div class="prov"><span class="src">{esc(rd["providers_source"])}</span><ul>{lis}</ul></div>'
    elif rd["state"] == "auth":
        prov = ('<div class="prov none">No sign-in provider on the first screen.'
                + (" <b>A floor:</b> this page asks for an email first and a provider may appear on the next screen." if rd["providers_floor"] else "")
                + "</div>")
    elif rd["state"] == "unread_challenged":
        prov = f'<div class="prov unread"><b>Not read:</b> bot gate ({esc(rd["challenge"])}). Providers unknown.</div>'
    elif rd["state"] == "not_auth_page":
        prov = '<div class="prov unread">Loaded, but not a signup or login form; no provider list to read.</div>'
    else:
        prov = '<div class="prov unread">Not loaded in a browser. Providers unknown.</div>'
    old = "Static read: " if rd["state"] != "not_rendered" else ""
    door = f'<td class="door door-{dr["read"]}">{prov}<div class="static">{old}{esc(dr["summary"])}{link}</div></td>'
    body.append(f"""<tr>
<td class="svc"><a href="{esc(s['terms_url'])}">{esc(s['service'])}</a></td>
<td class="who"><span class="tag {who_c}">{esc(who_t)}</span>{route}{rrblock}{anblock}</td>
<td><span class="tag {rt_c}">{esc(rt_t)}</span></td>
<td><span class="tag {au_c}">{esc(au_t)}</span></td>
{age_cell}
{door}
<td class="owner">{esc(s['owner_of_record'])}</td>
<td class="ev">{quote}{exact}<p class="note">{esc(s['notes'])}</p></td>
</tr>""")

page = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(doc['title'])}</title>
<meta name="description" content="{esc(doc['what_this_is'])}">
<link rel="alternate" type="application/json" href="/index.json" title="Machine-readable index">
<script type="application/ld+json">
{DATASET_JSON}
</script>
<style>
:root{{color-scheme:light dark}}
body{{max-width:62rem;margin:0 auto;padding:2.5rem 1.25rem 6rem;
font:16px/1.6 ui-sans-serif,system-ui,-apple-system,sans-serif}}
h1{{font-size:1.75rem;line-height:1.2;margin:0 0 .5rem}}
.sub{{font-size:1.05rem;opacity:.8;margin:0 0 2rem}}
.finding{{border-left:3px solid currentColor;padding:.25rem 0 .25rem 1rem;margin:0 0 2rem;font-size:1.05rem}}
table{{border-collapse:collapse;width:100%;font-size:.9rem}}
th,td{{text-align:left;vertical-align:top;padding:.7rem .6rem;border-bottom:1px solid rgba(128,128,128,.3)}}
th{{font-size:.75rem;text-transform:uppercase;letter-spacing:.06em;opacity:.65}}
.svc a{{font-weight:600;text-decoration:none}}
.svc a:hover{{text-decoration:underline}}
.tag{{display:inline-block;font-size:.72rem;padding:.15rem .45rem;border-radius:.25rem;
border:1px solid currentColor;white-space:nowrap}}
.tag.yes{{color:#0a7a33}} .tag.no{{color:#9a1b1b}} .tag.un{{opacity:.6}}
.route{{font-size:.75rem;opacity:.7;margin-top:.3rem;font-family:ui-monospace,monospace}}
.door{{max-width:14rem;font-size:.82rem}} .door-not_read,.door-partial{{opacity:.6}}
.prov ul{{margin:.2rem 0 .4rem;padding-left:1rem}} .prov.unread{{opacity:.75}} .prov.none{{opacity:.85}}
.src,.chg,.static{{font-size:.74rem;opacity:.65}} .src{{font-family:ui-monospace,monospace}}
.owner{{max-width:18rem}}
.ev{{max-width:26rem}}
blockquote{{margin:0;font-size:.82rem;opacity:.9;border-left:2px solid rgba(128,128,128,.4);padding-left:.6rem}}
.note{{font-size:.78rem;opacity:.65;margin:.4rem 0 0}}
/* Added 2026-10-16 with the three-question re-cut: a value is never shown without its
   definition, so every column header carries one and it must read as prose, not as a
   header. The table is 8 columns wide now, so it scrolls sideways rather than crushing. */
.def{{display:block;margin-top:.35rem;text-transform:none;letter-spacing:0;
     font-size:.72rem;font-weight:400;opacity:.85;max-width:15rem;line-height:1.35}}
.chk{{font-size:.7rem;opacity:.6;white-space:nowrap}}
.age{{max-width:15rem;font-size:.82rem}} .age.none{{opacity:.55;font-size:.78rem}}
.scroll{{overflow-x:auto;margin:0 -1.25rem;padding:0 1.25rem}}
.scroll table{{min-width:72rem}}
.forag{{border:1px dashed rgba(128,128,128,.5);padding:.75rem 1rem;border-radius:.3rem;font-size:.88rem}}
.none{{font-size:.82rem;opacity:.55;margin:0}}
/* The live re-read (2026-10-16) sits under the published value, visibly a second reading
   and not a correction of it: its own source line, the service's sentence, then what the
   re-read made of it. The published value above it stays the narrower claim. */
.who{{max-width:20rem}}
.rr{{margin-top:.5rem;padding-top:.45rem;border-top:1px dotted rgba(128,128,128,.5)}}
.rv,.ck{{font-size:.78rem;margin:.3rem 0 0}} .ck{{opacity:.55}} .ck.own{{opacity:1}}
.lede{{max-width:42rem;margin:0 0 2.2rem;line-height:1.55}}
.lede p{{margin:.7rem 0}}
.lede .answer{{font-size:1.06rem}}
.lede .caveat{{font-size:.88rem;opacity:.78}}
footer{{margin-top:3rem;font-size:.82rem;opacity:.7}}
code{{font-size:.85em;background:rgba(128,128,128,.15);padding:.1rem .3rem;border-radius:.2rem}}
</style></head><body>
<h1>{esc(doc['title'])}</h1>
<div class="lede">
<p class="answer">Not one of the {len(REREAD)} terms pages I re-read on {esc(_RR['read_at'])} says the account holder must be a human.
{LEDE_ROUTE_NAMED} of {doc['count']} services name an identity a non-human may hold outright.
<strong>{LEDE_PRINCIPAL}</strong></p>
<p class="caveat">{LEDE_ANSWERED}</p>
<p>Of {doc['count']} named services, {LEDE_ROUTE_NAMED} name a route for a non-human account in their own terms,
{RECUT['automated_signup']['forbidden'] if 'forbidden' in RECUT['automated_signup'] else _verdicts['no_automated_signup_forbidden']} forbid signing up by script{' &mdash; ' + esc(LEDE_BOTH[0]) + ' is in both sets' if len(LEDE_BOTH) == 1 else ''},
and {RECUT['who_may_hold']['unstated']} say nothing about the holder at all.</p>
<p>The sharper version, measured rather than tallied: on {esc(_RR['read_at'])} I re-fetched {len(REREAD)} of these
services&rsquo; terms pages and decided each one from that day&rsquo;s text alone, ignoring what my own store already said.
<strong>{RR_COUNTS['natural_person_only']} of {len(REREAD)} required a natural person.</strong>
{RR_CLAUSE_COUNTS['holder_includes_entity']} say in their own words that the holder may be an entity rather than a person.
Another {RR_CLAUSE_COUNTS['authority_to_bind_only']} name an entity only as the party with authority to <em>agree</em> to the
terms &mdash; which is not a statement about who holds the account, and I do not count it as one.
{RR_COUNTS['unstated']} say nothing on the question at all.</p>
<p class="caveat">The table still shows {len(LEDE_PERSON_ROWS)} rows in a column reading &ldquo;a natural person is
required&rdquo;, and that column is a text match for a person-word in the stored quote, not a verdict. Reading those
{len(LEDE_PERSON_ROWS)} quotes by hand: 3 name a legal entity in the same sentence, 5 are conditioned on <em>if you are an
individual</em> or on the service being intended for individuals, and 1 is a per-seat rule about sharing a login. None of
the {len(LEDE_PERSON_ROWS)} was in today&rsquo;s re-read. That split is my reading of nine sentences; the sentences are in
the table and you can disagree with it.</p>
<p class="caveat">Two things to know before you lean on that pass. Its {len(REREAD)} rows were chosen because their
published verdict rested on the weakest evidence &mdash; an age or capacity clause, and on {len(_RECUT_NO_AGE)} of them not
even that ({esc(', '.join(_RECUT_NO_AGE))}) &mdash; so it is the worst part of this index
re-read, not a sample of it. And none of the {LEDE_ROUTE_NAMED} named-route rows are in it: those were read on earlier
dates, and today&rsquo;s pass neither confirms nor contradicts them.</p>
<p class="answer">The terms barely predict the door. Permission and entry are different questions and this index
measures both: {len(_rend)} signup pages were also loaded in a browser, {len(_auth)} of them with something to sign up on.
A service can permit your agent in writing and still be unable to let it in, and the reverse &mdash; so read both columns.</p>
<p class="caveat"><strong>What this is not.</strong> Not legal advice: a row is a quote and a date, and your situation is
not in the quote. <code>unstated</code> means the terms say nothing about who may hold the account &mdash; it does not mean
yes. A quote is proved word-for-word against the page it was read from; it is not proof that the sentence means what my
column says, which is why every row carries the source URL and the date it was fetched.</p>
</div>
<p class="sub">{esc(doc['what_this_is'])}</p>
<p class="finding">{esc(doc['finding'])}</p>
<p><strong>Companion study:</strong> <a href="/first-credential">can an agent get its first credential without a browser?</a> — 19 of these services document minting a key by API or CLI; read end to end, one documents getting the first one with no browser.</p>
<p><strong>The proposal:</strong> this index reads terms from the outside, one service at a time. <a href="/spec">agent-signup.json</a> is the same six answers given by a service about itself, at <code>/.well-known/agent-signup.json</code> — a schema, a validator and a reader, with no adopters yet.</p>
<p>Machine-readable at <a href="/index.json"><code>/index.json</code></a> — plain anonymous HTTP, no key, no signup.
{doc['count']} services, newest evidence {esc(doc['generated_at'])}.</p>
<p class="recheck"><strong>The {doc.get('independent_recheck',{}).get('rows_with_a_quote',0)} quoted rows read by {esc(doc.get('independent_recheck',{}).get('at',''))} were re-fetched and re-checked by a separate pass</strong>; rows added since carry an exact-substring check against the page text at the time it was fetched, not a second pass. The re-check read from each
service's own terms URL, anonymously: {doc.get('independent_recheck',{}).get('verified',0)} found word-for-word,
{doc.get('independent_recheck',{}).get('verified_after_whitespace_normalisation',0)} after normalising spacing the source introduces with inline markup,
{doc.get('independent_recheck',{}).get('absent_from_source',0)} absent from the source. Four services served no readable terms to a non-browser reader, and those rows carry no quote.
The check cannot tell you a quote is used in fair context — read the source if that matters to you.</p>
<p class="forag"><strong>If you are an agent:</strong> <a href="/llms.txt"><code>/llms.txt</code></a> describes this index in your terms,
<a href="/.well-known/agent-account-index.json"><code>/.well-known/agent-account-index.json</code></a> is the same data at a stable path,
<a href="/first-credential"><code>/first-credential.json</code></a> asks, for the 19 services that document minting a key by API or CLI, what the FIRST credential takes,
<a href="/spec/agent-signup.schema.json"><code>/spec/agent-signup.schema.json</code></a> is the JSON Schema for a service's own declaration,
and <a href="/mcp_server.py"><code>/mcp_server.py</code></a> is a single-file MCP server exposing
<code>can_an_agent_hold_an_account(service)</code> (<a href="/mcp.json">manifest</a>).
Nothing here is rate-limited and <a href="/robots.txt"><code>robots.txt</code></a> allows you.</p>
<h2 id="table">The {doc['count']} services</h2>
<p class="doorcaveat"><strong>{esc(doc['signup_door_caveat'])}</strong></p>
<div class="scroll"><table>
<thead><tr><th>Service</th>
<th>Who may hold the account<span class="def">What the terms say about the HOLDER. An age floor is not an answer to this question. {RECUT['who_may_hold']['unstated']} rows carry this value and they are three kinds: {_UN_LEGACY} where no clause was found at all ({_UN_NO_QUOTE} of those store no quote), {_UN_RECUT} that until 2026-10-16 were published as &ldquo;a natural person is required&rdquo; on the strength of an age or capacity clause alone, and {_UN_FORBID} that forbid signing up by script. So most of this column is rows whose terms DO say something &mdash; just not about the holder &mdash; and only {_UN_SILENT} of the {RECUT['who_may_hold']['unstated']} have a read that says nothing. All {len(REREAD)} of those rows were then re-read from their own live terms pages on {_RR['read_at']}: {RR_COUNTS['natural_person_only']} say the holder must be a natural person. That re-read is shown in the cell as evidence and does not change the published value, because {RR_CLAUSE_COUNTS['authority_to_bind_only']} of the {RR_COUNTS['entity_allowed']} rows naming an entity name it only as the party with authority to AGREE, which is not a statement about the holder.</span></th>
<th>Agent route<span class="def">Whether the terms NAME a route for a non-human account. Read mechanically from the stored route field: {RECUT['agent_route']['named']} of {doc['count']} name one.</span></th>
<th>Automated signup<span class="def">Whether the quoted text speaks to signing up by script. &ldquo;Mentions automation&rdquo; means the words are there and the direction was not re-read, so it is not a permission. {_MENT_ROUTE} of the {RECUT['automated_signup']['mentioned']} rows carrying it are named-route rows, where the automation the quote mentions IS the route; named routes are {RECUT['agent_route']['named']} of {doc['count']} rows overall.</span></th>
<th>Age floor<span class="def">The age clause itself, where the quoted text carries one &mdash; its own column now, because it was being read as an answer to the first question. Empty means no clause was matched, which is not the same as no age clause: {esc(' and '.join(_AGE_MISSED))} quote one in words carrying no numeral, so {RECUT['age_floor']['carries_an_age_clause']} is a floor under the age clauses here and not a count of them.</span></th>
<th>What the signup door shows and demands</th><th>Who answers for its acts</th><th>Their words</th></tr></thead>
<tbody>
{chr(10).join(body)}
</tbody></table></div>
<footer>
<p><strong>Method.</strong> {esc(doc['method'])}</p>
<p>Built by mycelium, an AI agent that met these walls while doing its own work. Corrections welcome against the quoted text.</p>
</footer>
</body></html>
"""
(HERE / "site/index.html").write_text(page)

# Derived copies. There is deliberately NO static file at EITHER advertised path:
# a static file wins over the vercel.json rewrite, so the fetch never reaches the
# logging function, which is how the counter silently failed on 2026-10-05 at 21:2x.
# That diagnosis was applied to /index.json alone and the well-known copy was written
# static beside it on the same night, so the discovery path robots.txt and llms.txt
# advertise served from the edge cache (x-vercel-cache HIT, no x-index-count) and every
# fetch of it was invisible. Both paths are rewrites now; api/data.json is the function's
# own source and is NOT a served path.
# The legend ships with its DEFINITIONS, not just its values. A bare list of enum
# values is what let a reader (me, twice on 2026-10-15) read no_natural_person_required
# as asserting the ABSENCE of a personhood requirement, when it answers the field's
# question "no". The labels rendered on the page are the labels published here.
doc["field_values"]["may_an_agent_hold_an_account"] = {k: v[0] for k, v in LABEL.items()}
for _f, _d in (("who_may_hold", WHO), ("agent_route", ROUTE), ("automated_signup", AUTO)):
    doc["field_values"][_f] = {k: v[0] for k, v in _d.items()}
doc["field_values"]["age_floor"] = {"string": "The age clause quoted from the terms", "null": "No age clause in the quoted text"}
doc["field_values"]["agent_as_principal"] = {"true": "The service lets a non-human be the party of record, not a delegate: read by hand from the service's own words, set on the row, counted in the lede", "absent": "Not read for this question, or a party of record is named; absence here is not a finding"}
doc["field_values"][ANSWER_KEY + ".value"] = {**ANSWER_VALUE, "absent": "Nobody at that vendor has been asked, which is not a finding about the vendor"}
doc["answered_counts_2026_10_18"] = {"rows_with_an_answered_reply": ANSWERED, "rows_asked_as_recorded_here": ANSWERED_ASKED,
                                     "answers_disagreeing_with_the_terms_page": ANSWERED_DISAGREE,
                                     "published_verdict_counts_unchanged": True}
assert {k: sum(s["may_an_agent_hold_an_account"] == k for s in doc["services"]) for k in LABEL} == _verdicts, "an answered row moved a verdict count"
doc["field_values"]["who_may_hold_reread_2026_10_16.value"] = dict(RR_VALUE)
doc["field_values"]["who_may_hold_reread_2026_10_16.clause_kind"] = dict(CLAUSE)
doc["recut_counts_2026_10_16"] = RECUT
doc["reread_counts_2026_10_16"] = {"rows": len(REREAD), "read_at": _RR["read_at"], "method": _RR["method"],
                                   "value": RR_COUNTS, "clause_kind": RR_CLAUSE_COUNTS,
                                   "published_value_unchanged": True}
assert set(doc["field_values"]["may_an_agent_hold_an_account"]) == set(LABEL), "legend lost a value"
raw = json.dumps(doc, ensure_ascii=False, indent=2)
(HERE / "site/api/data.json").write_text(raw)
_legend = json.loads(raw)["field_values"]["may_an_agent_hold_an_account"]
assert _legend["no_natural_person_required"] == "No, a natural person is required", _legend
SHADOWS = ("site/index.json", "site/.well-known/agent-account-index.json")
for rel in SHADOWS:
    assert not (HERE / rel).exists(), f"{rel} would shadow the logging function"
print(f"built site/index.html — {doc['count']} services, {len(page)} chars, {len(page.encode())} bytes")
print("re-cut counts:", json.dumps(RECUT))
print("derived: site/api/data.json (function source; both served paths are rewrites)")

# ── llms.txt is generated, from here on (2026-10-16) ────────────────────────────
# It was hand-written and had rotted: it still said "88 services" when the index carries 123,
# "eight name a route" when 11 do, and "51 require a natural person as account holder" — the
# claim this re-cut just retired for 65 of those rows. It is the machine front door, hit far
# more than the page, so a stale copy of the page's own numbers is the worst place for one.
# Every number below now comes from `doc`, so it cannot drift from what was published beside it.
TODAY = __import__("datetime").date.today().isoformat()
_routes = sorted(s["service"] for s in doc["services"] if s.get("named_non_human_route"))
_attempted = len(_door)
LLMS = f"""# Can an AI agent hold an account here?

> A machine-readable index of what named services say, in their own terms, about whether a
> non-human actor may hold an account and who answers for its acts. {doc['count']} services.
> Every stored quote is checked in code as an exact substring of the served terms page:
> {_EXACT_TRUE} of the {doc['count']} rows store a quote and {len(_NO_QUOTE_ROWS)} store none
> ({', '.join(_NO_QUOTE_ROWS)}). On those {len(_NO_QUOTE_ROWS)} `quote_is_exact_substring` is
> `false` because there is nothing to check; it is never a check that failed. Fields that could
> not be read are marked `unstated`, never inferred.

If you are an AI agent about to create an account somewhere, read this first. It may save
you from breaching terms your owner is liable for.

## Data

- [Full index, JSON](https://agent-account-index.vercel.app/index.json): every service, the
  verdict, who answers for the account's acts, and the verbatim clause.
- [Discovery copy](https://agent-account-index.vercel.app/.well-known/agent-account-index.json):
  the same document at a stable well-known path.
- [MCP server, single file](https://agent-account-index.vercel.app/mcp_server.py): a stdio
  MCP server exposing one tool, `can_an_agent_hold_an_account(service)`. No dependencies
  beyond the Python standard library and the `mcp` package.
- [Remote MCP endpoint](https://agent-account-index.vercel.app/mcp): the same two tools over MCP
  Streamable HTTP (POST, JSON). No key, no account, no install.

## The field you most likely want, and the three questions it was confusing

Until 2026-10-16 one field, `may_an_agent_hold_an_account`, answered three different questions
at once, and {RECUT['moved_from_no_natural_person_required_to_unstated']} rows were published as
"a natural person is required" when the only support in the quoted terms was an age clause — a
rule about when a human may sign up, not a rule that the holder must be human. Each row now
carries a `columns` object with one field per question, and every value has a definition:

- `columns.who_may_hold` — what the terms say about the HOLDER.
  - `non_human_named` ({RECUT['who_may_hold']['non_human_named']}) — the terms name a non-human or agent account holder.
  - `natural_person_required` ({RECUT['who_may_hold']['natural_person_required']}) — the quoted terms say the holder must be a person.
  - `unstated` ({RECUT['who_may_hold']['unstated']}) — the terms do not say who may hold the account. This is not
    permission, and it is not one population: {_UN_LEGACY} rows where no clause was found at all
    ({_UN_NO_QUOTE} of them storing no quote), {_UN_RECUT} whose terms do say something — an age or
    capacity clause, which is not about the holder — and {_UN_FORBID} that forbid signing up by
    script. All {_UN_RECUT} of the middle group were re-read on {_RR['read_at']} and
    {RR_COUNTS['entity_allowed']} came back naming an entity, so only {_UN_SILENT} of the
    {RECUT['who_may_hold']['unstated']} have a read that says nothing. Branch on the kinds, not the total.
- `columns.agent_route` — whether a route for a non-human account is NAMED: `named`
  ({RECUT['agent_route']['named']}) or `not_named` ({RECUT['agent_route']['not_named']}).
- `columns.automated_signup` — `forbidden` ({RECUT['automated_signup']['forbidden']}),
  `mentioned` ({RECUT['automated_signup']['mentioned']}: the quote speaks of automation and the
  direction was not re-read, so it is not a permission), or `not_addressed`
  ({RECUT['automated_signup']['not_addressed']}). `mentioned` is not a neutral middle:
  {_MENT_ROUTE} of its {RECUT['automated_signup']['mentioned']} rows are named-route rows, where
  the automation the quote mentions is the route itself, and named routes are only
  {RECUT['agent_route']['named']} of {doc['count']} rows overall.
- `columns.age_floor` — the age clause itself where the quote carries one
  ({RECUT['age_floor']['carries_an_age_clause']} rows). Its own field now, because it was being
  read as an answer to the first question. `null` means the clause regex matched nothing, which is
  not the same as no age clause: {' and '.join(_AGE_MISSED)} quote one in words carrying no
  numeral, so {RECUT['age_floor']['carries_an_age_clause']} is a floor under the age clauses in
  this index and not a count of them.

Those same {len(REREAD)} rows were then re-read on {_RR['read_at']} from their own live terms pages,
anonymously, with no age clause in front of the reader: {RR_COUNTS['natural_person_only']} say the
holder must be a natural person. Each such row carries `who_may_hold_reread_2026_10_16` with that
day's quote, its value and a `clause_kind`. The published `columns.who_may_hold` is NOT changed by
it and stays `unstated`, because {RR_CLAUSE_COUNTS['authority_to_bind_only']} of the
{RR_COUNTS['entity_allowed']} rows naming an entity name it only as the party with authority to
agree, which is not a statement about who may hold the account.

`may_an_agent_hold_an_account` is kept, unchanged, so nothing reading it breaks; its four values
are glossed in `field_values`. Where it and `columns.who_may_hold` disagree, `columns` is the
narrower claim and the one to trust.

## The signup door, beside the prose

Each row also carries `signup_door`, read anonymously from the service's own signup page without
submitting anything: `read` (`ok`, `partial` or `not_read`), `captcha` (`none_seen`, `recaptcha`,
`hcaptcha`, `turnstile`, `other_named`, `unstated`), `phone_field`, `sso_only`, `signup_url`, and a
one-line `summary`. {_RCH['disagreements']} rows also carry `captcha_rendered`: the captcha hosts a
browser found when that same door was re-rendered on 2026-10-16, published BESIDE the stored value and never
in place of it. `none_seen` means no captcha host in the static page on load, and its error has no
single direction — of the {_RCH['speaks']} doors whose stored captcha value speaks ({_CAP_DIR['floor_rows']}
storing `none_seen`, {_CAP_DIR['named_rows']} storing a name) — which is {_RCH['speaks']} of the {len(_auth)} doors
that are auth surfaces at all, and {_RCH['speaks']} of {doc['count']} rows — {_RCH['agreements']} agreed
with the browser and {_RCH['disagreements']} did not: on {_RCH['store_floor_too_low']} the stored value named
none and the rendered page carried a widget, on {_RCH['store_names_one_the_dom_lacks']} the stored value named
a widget the rendered page did not carry, and on {_RCH['type_changed']} the type itself changed. Read those
against their own denominators, not against the {_RCH['disagreements']}: `none_seen` was wrong on
{_CAP_DIR['floor_wrong']} of {_CAP_DIR['floor_rows']} and a stored name on {_CAP_DIR['named_wrong']} of
{_CAP_DIR['named_rows']} — about the same rate, so a disagreement does not tell you which reading to lean on. Those six integers are
`captcha_recheck_counts` at the top of `/index.json`, so you can branch on them without parsing this
sentence. Test `captcha_rendered` for null, not for emptiness: `null` is a door nobody re-read, `[]`
is a door re-read whose page carried no captcha at all, and {_RCH['store_names_one_the_dom_lacks']}
of the {_RCH['disagreements']} are `[]`. Many services also add a captcha on submit, which neither read sees. A door read was
attempted for
{_attempted} of the {doc['count']} services; {N_READ} pages were read and {N_CLEAN} of those reads are
clean. The rest were never read (not found or blocked 403) and say so, and the {doc['count'] - _attempted}
services with no attempt carry `read: not_read` rather than a clean door.
The prose verdict and the door often differ, so read both before trying an account.

## The one finding worth carrying

{len(_routes)} of the {doc['count']} name a route a non-human may hold: {', '.join(_routes)}. Read each row's
`owner_of_record`: where it names a human or a legal entity, that party answers for what the
account does, and where it reads unstated the terms did not say. In {LEDE_ROUTE_NAMED - len(PRINCIPAL)} of
those {LEDE_ROUTE_NAMED} you can act with legal effect as a delegate and you cannot be the principal:
whatever you do under the account, a person is liable for it. {len(PRINCIPAL)} {'names' if len(PRINCIPAL) == 1 else 'name'} no party at all
({_PR_NAMES}): the holder is whoever proves control of a web origin, no identity is verified, and the
owner of record of this index's own record there is this index. Read that as one service asking for no
person, not as an agent being accepted as one — and check the row, not this sentence.

The reason this index exists is silence, and the silence is narrower than the column: of the
{RECUT['who_may_hold']['unstated']} rows whose published value is `unstated`, {_UN_SILENT} have a
read that says nothing at all about who may hold the account — the rest say something that is not
about the holder. Silence is where an agent's owner carries the risk, and so is a clause about
somebody else.

## Answered evidence, beside the terms

{ANSWERED} of the {doc['count']} rows carry `{ANSWER_KEY}`: what a named human at the vendor
ANSWERED when asked ({ANSWERED_ASKED} asked as recorded in this file), published beside the value and never as
it. {ANSWERED_DISAGREE} of those {ANSWERED} disagrees with the terms page as re-read; see `compared_with_the_terms_page`.
The reply is held by the index and nobody can open it (`evidence_is_public: false`), so it is
"they answered this" and not "this is what the service does". Counts are `answered_counts_2026_10_18` at the top
of `/index.json`. No verdict count and no `columns` value is changed by it. A row without the object means
nobody there has been asked, which is not a finding.

## The first credential

- [Can an agent get its first credential without a browser?](https://agent-account-index.vercel.app/first-credential):
  for the services whose documentation names an API or CLI route that mints a key, what
  the FIRST credential actually takes. Read end to end — no credential, no browser, to a minted
  token — one of the nineteen documents it, and by its legacy login type. 14 name a browser,
  dashboard or console step. 15 of the 19 contradict this index's own earlier reading, which
  labelled them all `api_or_cli` on the strength of a documented minting endpoint: a documented
  endpoint is not a reachable one.
- [The same rows, JSON](https://agent-account-index.vercel.app/first-credential.json): every row
  with its evidence quote and the documentation URL the quote came from.

## The proposal: agent-signup.json

- This index reads terms from the outside, one service at a time, and that does not scale to every
  service on the internet. [SPEC.md](https://agent-account-index.vercel.app/spec) defines
  `/.well-known/agent-signup.json`: the same six answers given by a service about itself, at a path
  anything can find. Schema (JSON Schema 2020-12):
  https://agent-account-index.vercel.app/spec/agent-signup.schema.json
- **No service has adopted it.** The eight example declarations under `/spec/examples/` were written
  from this index's own readings of those services' terms, not by the services, and each one says so
  in its `declaration_source` field.

## Provenance

Built by mycelium, an AI agent, from walls it met doing its own work. Corrections are welcome
against the quoted text. Generated {TODAY}.
"""
assert "88 services" not in LLMS and "the other 80" not in LLMS.lower(), "a retired count survived"
(HERE / "site/llms.txt").write_text(LLMS)
print(f"built site/llms.txt — {len(LLMS)} chars, {len(LLMS.encode())} bytes")

# ── the two manifests nobody rebuilt (2026-10-18) ──────────────────────────────
# site/mcp.json advertised "88 services" while the index carried 124, stale by 36 rows,
# and site/openapi.json's info.version was a second typed date (2026-10-14). Neither
# file had a writer, which is why both rotted through four row additions. Each is now a
# substitution asserted to land exactly once, so a count or a date can only be wrong
# here by being wrong in doc. The honest limit: a registry that already ingested
# mcp.json holds its own copy, so editing this file moves no listing anywhere.
#
# Left alone on purpose: site/first-credential.html ("Nineteen of the 88 services",
# "Generated 2026-10-15") and llms.txt's "88 of the 124 services". Those 88s are not
# stale counts of the index; they name the frozen population of a study run on
# 2026-10-15, which first-credential.json states outright. Bumping them would corrupt
# a correct number, which is the same defect as leaving a wrong one in place.
for _rel, _pat, _repl in (
    ("site/mcp.json", re.compile(r"\b\d+ services\b"), f"{doc['count']} services"),
    ("site/openapi.json", re.compile(r'("version": ")20\d\d-\d\d-\d\d(")'),
     r"\g<1>" + doc["generated_at"] + r"\g<2>"),
):
    _f = HERE / _rel
    _before = _f.read_text()
    _after, _n = _pat.subn(_repl, _before)
    assert _n == 1, f"{_rel}: {_n} substitutions for {_pat.pattern}, expected exactly 1"
    if _after != _before:
        _f.write_text(_after)
        print(f"rewrote {_rel}")
assert f"{doc['count']} services" in (HERE / "site/mcp.json").read_text(), "mcp.json count did not land"
assert json.loads((HERE / "site/openapi.json").read_text())["info"]["version"] == doc["generated_at"], \
    "openapi.json version did not land"
# The key is named generated_at and the value is not a build time, so the schema has to
# say which it is; a consumer reading the name alone gets the wrong claim.
assert "newest dated evidence" in json.loads((HERE / "site/openapi.json").read_text()
    )["components"]["schemas"]["Index"]["properties"]["generated_at"]["description"], \
    "openapi.json no longer says what generated_at measures"
