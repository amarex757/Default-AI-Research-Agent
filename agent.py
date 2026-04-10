"""
Default Research Agent (Gemini Version)
========================================
Takes a company domain as input, researches the account using live web search,
evaluates ICP fit for Default, identifies the right buyer persona, and generates
a targeted 3-email outbound sequence.

Usage:
    python agent.py --domain merge.dev --send-email
    python agent.py --domain usepylon.com --send-email
    python agent.py --domain listenlabs.ai --save
"""

import argparse
import json
import smtplib
import sys
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from google import genai
from google.genai import types

# ── Default ICP context injected into every prompt ───────────────────────────
DEFAULT_CONTEXT = """
You are a research agent for Default (default.com) — a B2B SaaS company that provides
revenue operations automation. Default is the control layer that sits between a company's
CRM (Salesforce, HubSpot) and their GTM stack.

Default's core capabilities:
- Lead routing: Automatically qualify, enrich, and route inbound leads to the right rep
- Scheduling: Connect high-intent leads directly to AE calendars with smart logic
- Workflow automation: Replace fragmented Zapier/Chili Piper/LeanData stacks
- CRM sync: Bi-directional Salesforce/HubSpot integration with a unified data model
- Waterfall enrichment: Layer multiple data sources to enrich leads automatically
- Intent tracking: Website visitor identification and behavioral signals

Default's ideal customer profile (ICP):
- Stage: Series A to Series C B2B SaaS companies
- Team: RevOps, Marketing Ops, or Growth teams with inbound volume
- Motion: Sales-led or hybrid PLG/sales-led (NOT pure PLG with no sales team)
- Stack: Already on Salesforce or HubSpot, using point solutions like Chili Piper, LeanData, Zapier
- Pain: Misrouted leads, slow speed-to-lead, broken integrations, RevOps spending time firefighting
- Size: Typically 50–1000 employees, with at least a small dedicated sales team

Default commonly replaces: Chili Piper, LeanData, Zapier (for GTM workflows), Clearbit Forms

ICP fit scoring rubric (score each dimension 1-5):
1. Company stage fit (Series A-C SaaS = 5, enterprise/pre-seed = lower)
2. Sales motion fit (sales-led or hybrid = 5, pure PLG = 2)
3. Stack complexity (using multiple point solutions = 5, simple setup = 2)
4. Team size fit (50-500 employees = 5, too small or too large = lower)
5. Pain signal strength (clear RevOps pain = 5, no obvious pain = 1)

Buyer personas at Default's ICP companies (in priority order):
1. Head of Revenue Operations / RevOps Manager — primary buyer, owns the stack
2. VP/Director of Marketing or Growth — owns inbound funnel and conversion
3. Head of Sales / CRO — cares about speed-to-lead and rep efficiency
4. Founder/CEO (at early-stage) — wears many hats including RevOps

Guardrails:
- If overall fit score is below 12/25, flag as WEAK FIT and adjust email tone
- Label inferences clearly — distinguish what you found vs. what you inferred
- Never fabricate specific metrics or claims about the prospect company
- Every email must reference at least one specific researched fact about the company
- Do not claim Default features that aren't listed above
"""


def call_gemini(prompt: str, client: genai.Client, use_search: bool = False) -> str:
    """Call Gemini with optional Google Search grounding."""
    tools = [types.Tool(google_search=types.GoogleSearch())] if use_search else []
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=DEFAULT_CONTEXT + "\n\n" + prompt,
        config=types.GenerateContentConfig(tools=tools)
    )
    return response.text


def research_and_generate(domain: str, client: genai.Client) -> dict:
    """
    Core agent loop: research company, evaluate fit, identify persona, generate emails.
    """

    print(f"\n{'='*60}")
    print(f"  Default Research Agent — {domain}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # ── Phase 1: Research ──────────────────────────────────────────────────────
    print("🔍 Phase 1: Researching company...")

    research_prompt = f"""
Search the web and research the company at domain: {domain}

Gather enough information to evaluate whether this company is a good fit
for Default (our RevOps automation platform) and identify the right buyer persona.

Research and document:

1. COMPANY BASICS
   - What does the company do? (one clear sentence)
   - Business model (B2B SaaS, marketplace, etc.)
   - Approximate headcount
   - Funding stage and recent rounds if available

2. GTM MOTION
   - Do they have a sales team? (inbound, outbound, or hybrid?)
   - Do they have a self-serve / PLG motion?
   - Any signals about their inbound volume or growth rate?

3. TECH STACK SIGNALS
   - What CRM do they likely use? (look for job postings, integrations pages)
   - Any signals about their marketing stack (HubSpot, Marketo, etc.)?
   - Any mentions of scheduling tools, routing tools, or RevOps tooling?

4. PAIN SIGNALS
   - Are they hiring for RevOps, Marketing Ops, or Sales Ops roles?
   - Any public mentions of growth challenges or scaling GTM?
   - Recent funding that would drive GTM scaling?

5. KEY PEOPLE
   - Who leads Revenue Operations, Marketing Operations, or Growth?
   - Who is VP/Head of Sales or Marketing?
   - Find names and titles where possible

Label inferences clearly — distinguish confirmed facts from reasonable inferences.
"""

    research_text = call_gemini(research_prompt, client, use_search=True)
    print("✅ Research complete\n")

    # ── Phase 2: Fit Evaluation ────────────────────────────────────────────────
    print("📊 Phase 2: Evaluating ICP fit...")

    fit_prompt = f"""
Based on this research about {domain}:

{research_text}

Evaluate this company's fit for Default using the ICP scoring rubric.

Score each dimension 1-5 and explain your reasoning:
1. Company stage fit
2. Sales motion fit
3. Stack complexity
4. Team size fit
5. Pain signal strength

Then:
- Calculate total score out of 25
- Give a FIT RATING: STRONG (20-25), MODERATE (12-19), or WEAK (<12)
- Write a 2-3 sentence fit summary
- Identify the PRIMARY buyer persona to target
- Identify 1-2 SPECIFIC pain points to lead with in outreach

Return ONLY valid JSON in exactly this format with no other text, no markdown, no backticks:
{{
  "scores": {{
    "stage_fit": 0,
    "sales_motion_fit": 0,
    "stack_complexity": 0,
    "team_size_fit": 0,
    "pain_signal_strength": 0
  }},
  "total_score": 0,
  "fit_rating": "STRONG",
  "fit_summary": "summary here",
  "primary_persona": {{
    "title": "job title",
    "name": null,
    "why_this_persona": "one sentence"
  }},
  "pain_points": ["pain point 1", "pain point 2"],
  "key_research_facts": ["fact 1", "fact 2", "fact 3"]
}}
"""

    fit_text = call_gemini(fit_prompt, client, use_search=False)

    # Parse fit evaluation
    try:
        clean = fit_text.strip()
        if "```" in clean:
            parts = clean.split("```")
            for part in parts:
                if "{" in part:
                    clean = part.replace("json", "").strip()
                    break
        fit_data = json.loads(clean)
    except json.JSONDecodeError:
        print("⚠️  Warning: Could not parse fit evaluation as JSON. Using fallback.")
        fit_data = {
            "fit_rating": "MODERATE",
            "total_score": 15,
            "fit_summary": fit_text[:300],
            "pain_points": ["RevOps complexity", "Lead routing gaps"],
            "primary_persona": {"title": "Head of RevOps", "name": None, "why_this_persona": "Owns the GTM stack"},
            "key_research_facts": ["B2B SaaS company", "Has a sales team", "Uses CRM"],
            "scores": {"stage_fit": 3, "sales_motion_fit": 3, "stack_complexity": 3, "team_size_fit": 3, "pain_signal_strength": 3}
        }

    # Print fit summary
    rating = fit_data.get("fit_rating", "UNKNOWN")
    score = fit_data.get("total_score", "?")
    emoji = {"STRONG": "🟢", "MODERATE": "🟡", "WEAK": "🔴"}.get(rating, "⚪")
    print(f"{emoji} Fit Rating: {rating} ({score}/25)")
    print(f"   {fit_data.get('fit_summary', '')}\n")

    if rating == "WEAK":
        print("⚠️  WEAK FIT — emails generated but flagged. Review before sending.\n")

    # ── Phase 3: Email Generation ──────────────────────────────────────────────
    print("✉️  Phase 3: Generating email sequence...")

    persona = fit_data.get("primary_persona", {})
    pain_points = fit_data.get("pain_points", [])
    key_facts = fit_data.get("key_research_facts", [])

    email_prompt = f"""
Generate a 3-email outbound sequence for {domain}.

TARGET PERSONA: {persona.get('title', 'Head of RevOps')}
{f"CONTACT NAME: {persona['name']}" if persona.get('name') else ""}

KEY PAIN POINTS TO ADDRESS:
{chr(10).join(f"- {p}" for p in pain_points)}

SPECIFIC COMPANY FACTS TO REFERENCE (use at least one per email):
{chr(10).join(f"- {f}" for f in key_facts)}

FIT RATING: {rating}
FIT SUMMARY: {fit_data.get('fit_summary', '')}

Email guidelines:
- Email 1 (Day 1): Cold intro. Lead with their specific pain, not our product.
  4-6 sentences. Reference one specific company detail. Soft CTA.

- Email 2 (Day 4): Value add. Share a relevant insight or customer story.
  Medium length. Position Default as the solution without being pushy.

- Email 3 (Day 10): Breakup email. Honest, direct, low-pressure. 3-4 sentences.

Tone: Direct, human, not salesy. No buzzwords. No "hope this finds you well."
Start with something specific and relevant to their business.

{"NOTE: WEAK FIT account. Be more exploratory and less assumptive." if rating == "WEAK" else ""}

Return ONLY valid JSON with no other text, no markdown, no backticks:
{{
  "email_1": {{
    "subject": "subject line",
    "body": "email body",
    "send_day": 1
  }},
  "email_2": {{
    "subject": "subject line",
    "body": "email body",
    "send_day": 4
  }},
  "email_3": {{
    "subject": "subject line",
    "body": "email body",
    "send_day": 10
  }}
}}
"""

    email_text = call_gemini(email_prompt, client, use_search=False)

    try:
        clean = email_text.strip()
        if "```" in clean:
            parts = clean.split("```")
            for part in parts:
                if "{" in part:
                    clean = part.replace("json", "").strip()
                    break
        email_data = json.loads(clean)
    except json.JSONDecodeError:
        print("⚠️  Warning: Could not parse emails as JSON.")
        email_data = {}

    print("✅ Email sequence generated\n")

    return {
        "domain": domain,
        "research": research_text,
        "fit_evaluation": fit_data,
        "emails": email_data,
        "generated_at": datetime.now().isoformat()
    }


def print_results(results: dict):
    """Pretty print results to terminal."""
    fit = results["fit_evaluation"]
    emails = results["emails"]
    domain = results["domain"]

    print(f"\n{'='*60}")
    print(f"  RESULTS FOR: {domain}")
    print(f"{'='*60}\n")

    # Fit scores
    print("📊 ICP FIT EVALUATION")
    print("-" * 40)
    scores = fit.get("scores", {})
    score_labels = {
        "stage_fit": "Company Stage",
        "sales_motion_fit": "Sales Motion",
        "stack_complexity": "Stack Complexity",
        "team_size_fit": "Team Size",
        "pain_signal_strength": "Pain Signals"
    }
    for key, label in score_labels.items():
        score = scores.get(key, 0)
        bar = "█" * int(score) + "░" * (5 - int(score))
        print(f"  {label:<22} {bar}  {score}/5")

    rating = fit.get("fit_rating", "UNKNOWN")
    total = fit.get("total_score", "?")
    emoji = {"STRONG": "🟢", "MODERATE": "🟡", "WEAK": "🔴"}.get(rating, "⚪")
    print(f"\n  {emoji} Overall: {rating} ({total}/25)")
    print(f"\n  Summary: {fit.get('fit_summary', '')}")

    persona = fit.get("primary_persona", {})
    print(f"\n  Target Persona: {persona.get('title', 'Unknown')}")
    if persona.get("name"):
        print(f"  Contact Name:   {persona['name']}")

    print(f"\n  Pain Points:")
    for p in fit.get("pain_points", []):
        print(f"    • {p}")

    # Emails
    print(f"\n\n✉️  OUTBOUND EMAIL SEQUENCE")
    print("-" * 40)
    for key in ["email_1", "email_2", "email_3"]:
        if key not in emails:
            continue
        email = emails[key]
        print(f"\n📧 Email {key[-1]} — Send Day {email.get('send_day', '?')}")
        print(f"   Subject: {email.get('subject', '')}")
        print(f"\n{email.get('body', '')}\n")
        print("-" * 40)


def send_email(results: dict, smtp_host: str, smtp_port: int,
               smtp_user: str, smtp_password: str, to_email: str = "sidd@default.com"): 
    """Send Email 1 to the specified address."""
    emails = results.get("emails", {})
    email_1 = emails.get("email_1", {})

    if not email_1:
        print("❌ No Email 1 found to send.")
        return

    domain = results["domain"]
    fit_rating = results["fit_evaluation"].get("fit_rating", "UNKNOWN")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Default Agent Demo | {domain} | {fit_rating}] {email_1.get('subject', '')}"
    msg["From"] = smtp_user
    msg["To"] = to_email

    body_text = f"""
--- DEFAULT RESEARCH AGENT OUTPUT ---
Domain researched: {domain}
Fit rating: {fit_rating} ({results['fit_evaluation'].get('total_score', '?')}/25)
Target persona: {results['fit_evaluation'].get('primary_persona', {}).get('title', 'Unknown')}
Generated at: {results['generated_at']}
Model: Gemini 2.0 Flash with Google Search grounding
--------------------------------------

SIMULATED EMAIL (what would be sent to the prospect):

Subject: {email_1.get('subject', '')}

{email_1.get('body', '')}
"""
    msg.attach(MIMEText(body_text, "plain"))

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
        print(f"\n✅ Email sent to {to_email}")
    except Exception as e:
        print(f"\n❌ Failed to send email: {e}")
        print("   Check your SMTP credentials in .env")


def save_results(results: dict, domain: str):
    """Save full results to JSON."""
    filename = f"output_{domain.replace('.', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n💾 Full results saved to: {filename}")


def main():
    parser = argparse.ArgumentParser(description="Default Research Agent (Gemini)")
    parser.add_argument("--domain", required=True, help="Company domain (e.g. merge.dev)")
    parser.add_argument("--send-email", action="store_true", help="Send Email 1 to sidd@default.com")
    parser.add_argument("--save", action="store_true", help="Save results to JSON file")
    args = parser.parse_args()

    # Load .env
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY not found. Set it in your .env file.")
        print("   Get a free key at: https://aistudio.google.com/apikey")
        sys.exit(1)

    # Init Gemini
    client = genai.Client(api_key=api_key)

    # Run agent
    results = research_and_generate(args.domain, client)
    print_results(results)

    if args.save:
        save_results(results, args.domain)

    if args.send_email:
        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "465"))
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")

        if not smtp_user or not smtp_password:
            print("\n⚠️  SMTP credentials not found — skipping email send.")
            print("   Add SMTP_USER and SMTP_PASSWORD to your .env to enable sending.")
        else:
            send_email(results, smtp_host, smtp_port, smtp_user, smtp_password)


if __name__ == "__main__":
    main()
