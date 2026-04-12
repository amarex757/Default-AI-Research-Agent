# Default AI Research Agent

A three-phase AI research agent which takes a company domain as input, researches the account using live web search, evaluates ICP fit for Default, identifies the right buyer persona, and generates a targeted 3-email outbound sequence.
<img src="/sales-agent.jpg" width="50%">
---

## What It Does

The core problem this agent solves: a good SDR spends 30–45 minutes researching one company before a cold call — checking fit, finding the right buyer, writing something specific. That doesn't scale. This agent does the same thing in under a minute.

The goal isn't to replace rep judgment. It's to eliminate the grunt work so by the time a rep sees a lead, the research is done, fit is scored, and the first email is drafted. The rep's job is to review and send.

---

## Architecture

The agent runs in three deliberately separated phases:

```
agent.py
├── Phase 1: Research         → Live web search via Gemini + Google Search grounding
├── Phase 2: Fit Evaluation   → Structured ICP scoring (JSON output)
└── Phase 3: Email Generation → Personalized 3-email outbound sequence
```

### Why Three Separate API Calls?

Each phase is doing a fundamentally different job:

- **Research** is open-ended exploration — the model needs to reason about what to look for based on what it finds
- **Fit evaluation** needs clean, structured JSON output that feeds programmatically into the next step
- **Email generation** is creative writing that requires both research and fit data as context

Collapsing these into one prompt produces mediocre results at all three. Separating them lets each phase be optimized independently. The tradeoff is latency (~60–90 seconds end to end), which is acceptable for an on-demand research tool.

---

## Model & API

**Model:** `gemini-flash-latest` via the [Google Gemini API](https://aistudio.google.com)

**Why Gemini:**
- Free tier with no credit card required via Google AI Studio
- Native Google Search grounding — Phase 1 pulls live web data rather than relying on training data that could be months out of date
- Fast inference suitable for a multi-phase agent

**Why live web search matters:**
Company information changes constantly — funding rounds, headcount, new hires, product launches. An agent making fit decisions based on stale training data will get things wrong. Google Search grounding ensures the research reflects the current state of the company.

**API usage by phase:**

| Phase | Search Grounding | Purpose |
|-------|-----------------|---------|
| Phase 1 — Research | ✅ Enabled | Live company intel |
| Phase 2 — Fit Evaluation | ❌ Disabled | Reason from Phase 1 output |
| Phase 3 — Email Generation | ❌ Disabled | Generate from Phase 1 + 2 output |

Search is only enabled in Phase 1 to keep latency down and ensure Phase 2 and 3 reason from a consistent research snapshot.

---

## ICP Context Layer

Before any research runs, Default's full ICP is injected into the system prompt:

- Ideal customer profile (Series A–C B2B SaaS, sales-led or hybrid motion)
- Fit scoring rubric (5 dimensions, 1–5 each, total out of 25)
- Buyer persona priority order (RevOps → Marketing Ops → Sales → Founder)
- Guardrails on what to flag vs. what to generate

This means the agent reasons against a known framework rather than guessing. If Default's ICP evolves, one block updates and the entire agent updates with it.

---

## Fit Scoring

The agent scores each account across five dimensions:

| Dimension | What It Measures |
|-----------|-----------------|
| Company Stage | Series A–C SaaS = 5, pre-seed or enterprise = lower |
| Sales Motion | Sales-led or hybrid = 5, pure PLG = 2 |
| Stack Complexity | Multiple point solutions = 5, simple setup = 2 |
| Team Size | 50–500 employees = 5, too small or too large = lower |
| Pain Signals | Active RevOps hiring, recent funding, public GTM pain = 5 |

**Fit ratings:**
- 🟢 STRONG: 20–25
- 🟡 MODERATE: 12–19
- 🔴 WEAK: below 12

---

## Guardrails

Two explicit guardrails are built into the agent:

**1. Fit threshold**
If a company scores below 12/25, the agent flags it as WEAK FIT and adjusts the email tone to be exploratory rather than assumptive. In production, you'd add a human review step before anything goes out on a weak fit account.

**2. Specificity requirement**
Every email must reference at least one specific researched fact about the company. This is a hard guardrail against generic copy — if the agent can't find enough to say something specific, it flags that rather than filling in the gaps with something vague.

---

## Sample Output

Running against `merge.dev`:

```
📊 ICP FIT EVALUATION
----------------------------------------
  Company Stage          █████  5/5
  Sales Motion           █████  5/5
  Stack Complexity       █████  5/5
  Team Size              █████  5/5
  Pain Signals           ████░  4/5

  🟢 Overall: STRONG (24/25)

  Summary: Merge is a textbook high-growth Series B SaaS with a complex
  hybrid GTM motion and a fragmented tech stack including Salesforce, Clay,
  and n8n. Their active hiring for Marketing Ops indicates high readiness
  for a unified orchestration layer.

  Target Persona: Director of Revenue Operations
  Contact Name:   Alex Kean
```

---

## Setup

### 1. Install dependencies
```bash
python3 -m pip install -r requirements.txt --break-system-packages
```

### 2. Get a free Gemini API key
Go to **https://aistudio.google.com/apikey** — free, no credit card needed.

### 3. Configure environment
```bash
cp .env.example .env
# Add your GEMINI_API_KEY to .env
```

Or export directly in terminal:
```bash
export GEMINI_API_KEY=your_key_here
```

---

## Usage

```bash
# Basic run — prints research, fit score, and emails to terminal
python3 agent.py --domain merge.dev

# Save full output to JSON
python3 agent.py --domain listenlabs.ai --save

# Send Email 1 to a specified address
python3 agent.py --domain merge.dev --send-email
```

---

## Sample Domains

| Company | Domain |
|---------|--------|
| Listen Labs | listenlabs.ai |
| Merge | merge.dev |
| Pylon | usepylon.com |
| Linear | linear.app |
| Tracksuit | gotracksuit.io |
| Owner | owner.com |

---

## What I'd Build Next

- **CRM integration** — output creates a Salesforce lead record with fit score and draft emails attached. Rep reviews in their CRM, not a terminal.
- **Sequencing hookup** — approved emails enroll in Outreach or Apollo automatically, not just drafted.
- **Feedback loop** — rep signals on lead quality feed back into the ICP scoring logic over time. Right now the ICP is static.
- **Batch mode** — run across a CSV of domains and output a ranked fit report. That's the real GTM use case at scale.
- **Confidence scoring** — the agent currently labels inferences vs. confirmed facts in prose. A formal confidence score per research field would make the fit evaluation more trustworthy at volume.

---

## Built With

- [Google Gemini API](https://aistudio.google.com) — gemini-flash-latest with Google Search grounding
- Python standard library (smtplib, json, argparse)
- [python-dotenv](https://pypi.org/project/python-dotenv/)
- [google-genai](https://pypi.org/project/google-genai/)
