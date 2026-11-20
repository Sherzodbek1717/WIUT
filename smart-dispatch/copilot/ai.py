"""Sean AI writing helpers: broker emails and call scripts.

Uses Claude when ANTHROPIC_API_KEY (or another Anthropic credential) is set, and
falls back to built-in templates otherwise, so the app always works. Callers get
`ai_used=False` when the template was used, so the interface can say so.
"""

import json
import logging
import os
from dataclasses import dataclass, field

from django.conf import settings

logger = logging.getLogger(__name__)

EMAIL_SCHEMA = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["subject", "body"],
    "additionalProperties": False,
}
CALL_SCHEMA = {
    "type": "object",
    "properties": {
        "opening": {"type": "string"},
        "questions": {"type": "array", "items": {"type": "string"}},
        "negotiation": {"type": "array", "items": {"type": "string"}},
        "closing": {"type": "string"},
    },
    "required": ["opening", "questions", "negotiation", "closing"],
    "additionalProperties": False,
}
SYSTEM = (
    "You write for a US trucking dispatcher who books freight from brokers. "
    "Be brief, friendly and professional, in plain American trucking language "
    "(MC number, rate con, deadhead, all-in rate). Never invent facts that are not in the load "
    "details; leave out anything unknown. Never promise anything the dispatcher did not state."
)


@dataclass
class EmailDraft:
    subject: str
    body: str
    ai_used: bool = False


@dataclass
class CallScript:
    opening: str
    questions: list = field(default_factory=list)
    negotiation: list = field(default_factory=list)
    closing: str = ""
    ai_used: bool = False


def ai_available():
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def load_facts(posting, user, dh_o=None, target_rate=None):
    """Plain facts about the load and the carrier, shared by every prompt and template."""
    facts = {
        "lane": f"{posting.origin_label} to {posting.destination_label}",
        "pickup": posting.pickup_date.strftime("%a %b %d"),
        "delivery": posting.delivery_date.strftime("%a %b %d") if posting.delivery_date else None,
        "equipment": posting.get_equipment_display() + (" (team)" if posting.team_required else ""),
        "weight": f"{posting.weight_lbs:,} lbs",
        "trip_miles": posting.trip_miles,
        "posted_rate": f"${posting.rate:,.0f}" if posting.rate else None,
        "reference": posting.reference or None,
        "broker": posting.company_name,
        "carrier": user.company_name or None,
        "mc_number": user.mc_number or None,
        "dispatcher": user.get_full_name() or user.username,
        "phone": user.phone or None,
        "email": user.email or None,
        "truck_distance_from_pickup_miles": dh_o,
        "dispatcher_target_rate": f"${target_rate:,.0f}" if target_rate else None,
    }
    return {k: v for k, v in facts.items() if v not in (None, "")}


def truck_location(posting, dh_o):
    """One sentence on where the truck is, or "" when unknown."""
    if dh_o is None:
        return ""
    if dh_o < 15:
        return f"My truck is already in {posting.origin_label}."
    return f"My truck is {dh_o} miles from the pickup."


def signature(facts):
    lines = [facts["dispatcher"]]
    if facts.get("carrier"):
        lines.append(facts["carrier"] + (f" | MC# {facts['mc_number']}" if facts.get("mc_number") else ""))
    if facts.get("phone"):
        lines.append(facts["phone"])
    return "\n".join(lines)


def template_email(posting, user, dh_o=None, target_rate=None):
    f = load_facts(posting, user, dh_o, target_rate)
    ref = f" (ref {f['reference']})" if f.get("reference") else ""
    subject = f"{posting.origin_label} → {posting.destination_label} {posting.pickup_date:%m/%d} – {f['equipment']} available"
    lines = [
        "Hello,",
        "",
        f"I have a {f['equipment'].lower()} available for your load {f['lane']}{ref}, picking up {f['pickup']}.",
    ]
    if dh_o is not None:
        lines.append(truck_location(posting, dh_o))
    if f.get("posted_rate") and target_rate:
        lines.append(f"Could you do {f['dispatcher_target_rate']} all-in? Posted rate shows {f['posted_rate']}.")
    elif target_rate:
        lines.append(f"What is your best rate? We can do it for {f['dispatcher_target_rate']} all-in.")
    else:
        lines.append("What is your best all-in rate for this one?")
    lines += ["", "If it works, please send the rate con and we will get it covered.", "", "Thank you,", signature(f)]
    return EmailDraft(subject=subject, body="\n".join(lines), ai_used=False)


def template_call_script(posting, user, dh_o=None, target_rate=None, walk_away=None):
    f = load_facts(posting, user, dh_o, target_rate)
    who = f"{f['dispatcher']} with {f['carrier']}" if f.get("carrier") else f["dispatcher"]
    mc = f", MC {f['mc_number']}" if f.get("mc_number") else ""
    ref = f", reference {f['reference']}" if f.get("reference") else ""
    negotiation = []
    if target_rate:
        negotiation.append(f"Ask for ${target_rate:,.0f} all-in first.")
    if walk_away:
        negotiation.append(f"Do not go below ${walk_away:,.0f} – that is break-even including deadhead.")
    if dh_o:
        negotiation.append(f"Mention the truck is {dh_o} mi out (empty miles cost money).")
    negotiation.append("If they won't move, ask about fuel surcharge, detention and quick pay.")
    return CallScript(
        opening=f"Hi, this is {who}{mc}. I'm calling about your {f['lane']} load picking up {f['pickup']}{ref}. Is it still available?",
        questions=[
            "What are the pickup and delivery appointment times?",
            "What's the commodity and exact weight?",
            "Any special requirements (tarps, TWIC, team, temp)?",
            "Is it drop and hook or live load/unload? How is detention paid?",
            "Who do I send our MC and insurance to for setup?",
        ],
        negotiation=negotiation,
        closing="Great, please send the rate con to " + (f["email"] if f.get("email") else "my email") + " and I'll confirm the driver right away.",
        ai_used=False,
    )


def _ask_claude(instructions, facts, schema):
    """One structured-output request. Returns the parsed dict, or None if Claude could not help."""
    import anthropic

    client = anthropic.Anthropic()
    try:
        response = client.beta.messages.create(
            model=settings.SEAN_AI_MODEL,
            max_tokens=16000,
            system=SYSTEM,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # retry on Anthropic's recommended model if a request is declined
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            messages=[{
                "role": "user",
                "content": f"{instructions}\n\nLoad and carrier details (JSON):\n{json.dumps(facts, indent=2)}",
            }],
        )
    except anthropic.AuthenticationError:
        logger.warning("Sean AI: the Anthropic API key was rejected; using templates.")
        return None
    except anthropic.RateLimitError:
        logger.warning("Sean AI: rate limited; using templates.")
        return None
    except anthropic.APIStatusError as exc:
        logger.warning("Sean AI: API error %s; using templates.", exc.status_code)
        return None
    except anthropic.APIConnectionError:
        logger.warning("Sean AI: could not reach the Anthropic API; using templates.")
        return None

    if response.stop_reason in ("refusal", "max_tokens"):
        logger.warning("Sean AI: response stopped with %s; using templates.", response.stop_reason)
        return None
    text = "".join(block.text for block in response.content if block.type == "text")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Sean AI: response was not valid JSON; using templates.")
        return None


def draft_email(posting, user, dh_o=None, target_rate=None, note=""):
    fallback = template_email(posting, user, dh_o, target_rate)
    if not ai_available():
        return fallback
    instructions = (
        "Write a short email (under 120 words) from the dispatcher to the broker asking to book this load. "
        "Mention the truck's distance from pickup if given, ask for the dispatcher_target_rate all-in if given "
        "(otherwise ask for their best rate), ask for the rate confirmation, and end with this signature exactly:\n"
        f"{signature(load_facts(posting, user))}\n"
        "Subject: lane, pickup date and equipment, under 80 characters."
    )
    if note:
        instructions += f"\nThe dispatcher also wants to say: {note}"
    data = _ask_claude(instructions, load_facts(posting, user, dh_o, target_rate), EMAIL_SCHEMA)
    if not data:
        return fallback
    return EmailDraft(subject=data["subject"][:200], body=data["body"], ai_used=True)


def draft_call_script(posting, user, dh_o=None, target_rate=None, walk_away=None):
    fallback = template_call_script(posting, user, dh_o, target_rate, walk_away)
    if not ai_available():
        return fallback
    facts = load_facts(posting, user, dh_o, target_rate)
    if walk_away:
        facts["walk_away_rate"] = f"${walk_away:,.0f}"
    instructions = (
        "Prepare a phone script for the dispatcher calling the broker about this load: a one-sentence opening "
        "(name, company, MC if given, the lane and pickup date), 4-6 short questions to confirm the load details, "
        "3-5 negotiation tips that use the target and walk-away rates if given, and a one-sentence closing asking "
        "for the rate confirmation."
    )
    data = _ask_claude(instructions, facts, CALL_SCHEMA)
    if not data:
        return fallback
    return CallScript(
        opening=data["opening"], questions=data["questions"][:8], negotiation=data["negotiation"][:8],
        closing=data["closing"], ai_used=True,
    )
