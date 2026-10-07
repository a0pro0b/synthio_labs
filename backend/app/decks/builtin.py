"""Built-in 6-slide Synthio Labs deck. HTML-rendered (no images); facts from synthiolabs.com."""

from app.decks.models import DeckManifest, Slide

BUILTIN_DECK_ID = "synthio-labs"

_SLIDES: list[dict] = [
    {
        "title": "Synthio Labs: The Agentic AI Platform for Life Sciences",
        "bullets": [
            "The intelligence layer behind modern life sciences engagement",
            "Compliant, continuous conversations across HCPs, patients and field teams",
            "Powers pharma GTM: HCP engagement, patient support, field enablement, "
            "marketing and commercial ops",
        ],
        "notes": (
            "Welcome the audience. Synthio Labs builds a multimodal, agentic AI platform "
            "purpose-built for pharma's most critical workflows. Their line is that the pharma "
            "teams of the future run on Synthio. Proof points from the site: 10B+ LLM tokens "
            "for pharma, 500K+ minutes of voice AI, 10K+ patients engaged and 99% CSAT."
        ),
    },
    {
        "title": "The Engagement Problem",
        "bullets": [
            "HCP, patient and field touchpoints are fragmented across tools and channels",
            "Engagement has to be continuous, not limited to office hours",
            "Every answer must stay on-label under strict compliance pressure",
            "Most pharma AI is stitched together: a voice vendor here, analytics there, "
            "compliance bolted on",
        ],
        "notes": (
            "Frame the problem. Life sciences teams talk to HCPs, patients and their own field "
            "reps through many disconnected systems, and people need answers outside business "
            "hours. Synthio's point is that most pharma AI deployments are stitched together, "
            "with compliance added as an afterthought, while every response must stay within "
            "approved, on-label content."
        ),
    },
    {
        "title": "Clinical-Grade Voice AI",
        "bullets": [
            "Engineered for medical nuance: it hears milligrams versus micrograms",
            "Handles branded drug names, complex regimens and molecular entities",
            "Answers grounded in clinical data and approved content, with citations",
            "Benchmarked on USMLE-style medical reasoning assessments",
        ],
        "notes": (
            "Synthio's voice AI uses an audio-to-intent pipeline tuned for medical vocabulary. "
            "It interprets evidence and nuanced HCP intent, and answers complex questions about "
            "dosing, safety logic and clinical tables, grounded in approved content. Under the "
            "hood: a clinical reasoning engine, a multimodal voice and chat layer, and knowledge "
            "graphs that ingest FDA labels, brand messaging, MOAs, PI and peer-reviewed "
            "literature. When in doubt, it asks rather than guesses."
        ),
    },
    {
        "title": "The Product Suite",
        "bullets": [
            "Jarvis: voice AI copilot for field teams",
            "Ather: voice AI agents for HCP engagement",
            "Helix: voice AI agents for patient support",
            "Simulation Studio: AI digital twins for market research",
            "Polaris HQ: talk to your data",
            "Atlas: the AI-ready HCP 360",
        ],
        "notes": (
            "Six products on one platform. Results quoted on the site: Helix drove 5,000+ "
            "patient conversations in 48 hours with a 9 out of 10 NPS for the AI nurse. Jarvis "
            "reached 90% weekly active usage and saved reps about 10 hours a week, deployed to "
            "a top-10 pharma immunology field team in 6 weeks. Simulation Studio showed 95%+ "
            "overlap with a human advisory board, 20% net-new insights, and 72-hour end-to-end "
            "simulations."
        ),
    },
    {
        "title": "Safe by Design: Built Around Pharma Compliance",
        "bullets": [
            "Every answer verified against approved label content (MLR-aligned)",
            "Safety signals detected and adverse events routed through compliant escalation",
            "Detailed audit logs for medical, legal and regulatory oversight",
            "No off-label discussion; SOC2, HIPAA and GDPR compliant",
        ],
        "notes": (
            "Compliance is designed in, not bolted on. Each response passes automated "
            "verification grounded in approved label content. Adverse events are detected and "
            "escalated through compliant workflows. Every call is logged, reviewable and "
            "deletable, audio is encrypted in transit and at rest, and conversations follow the "
            "brand's approved scientific narrative."
        ),
    },
    {
        "title": "Integrations, Omnichannel and Summary",
        "bullets": [
            "Syncs with Veeva, Salesforce, MedInfo systems, knowledge bases and CRM stacks",
            "One engine, consistent answers across phone, web, chat, QR and SMS",
            "A holistic customer-journey map across the engagement ecosystem",
            "Summary: clinical-grade voice, six products, compliance by design",
        ],
        "notes": (
            "Synthio acts as a system of context for modern customer engagement and customer "
            "experience. It plugs into Veeva, Salesforce and MedInfo, and gives consistent "
            "answers on every channel from one unified engine. Close with a recap: an agentic "
            "AI platform for life sciences with clinical-grade voice, a six-product suite, and "
            "safety and compliance by design. Then invite questions."
        ),
    },
]


def builtin_deck() -> DeckManifest:
    slides = [
        Slide(
            index=i,
            title=s["title"],
            bullets=s["bullets"],
            text="\n".join(s["bullets"]),
            notes=s["notes"],
        )
        for i, s in enumerate(_SLIDES)
    ]
    return DeckManifest(
        deck_id=BUILTIN_DECK_ID,
        name="Synthio Labs Overview",
        source="builtin",
        slides=slides,
    )
