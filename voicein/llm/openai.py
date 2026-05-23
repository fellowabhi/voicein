"""GPT-4o-mini formatting pass with configurable rewrite tiers."""

from __future__ import annotations


def _tier_block(level: int) -> str:
    if level <= 0:
        return (
            "Tier 0 (FORMAT ONLY):\n"
            "- Do NOT rephrase, reorder, synonym-swap, or improve wording stylistically.\n"
            "- Only remove benign filler words when safe.\n"
            "- Fix obvious transcription glitches when meaning is unmistakable.\n"
            "- Light punctuation/capitalization normalization only.\n"
            "- Honour spoken formatting commands exactly as described globally.\n"
        )
    if level <= 3:
        return (
            f"Tier {level}/10 LIGHT CLEANUP:\n"
            "- Grammar + clumsy wording fixes allowed with MINIMAL lexical edits.\n"
            "- Preserve speaker intent and specificity.\n"
        )
    if level <= 6:
        return (
            f"Tier {level}/10 PROMPT POLISH:\n"
            "- Moderate clarity improvements using ONLY voiced concepts.\n"
            "- If dictation resembles LLM prompting: prefer context→task→constraints structure.\n"
            "- Expand spoken enumerations (\"first… second…\") into hyphen bullets (- ).\n"
            "- Maintain imperative/directive tone unless speaker was conversational.\n"
            "- Absolutely no fabricated constraints, KPIs, security claims, timelines, repos, tooling, citation details the speaker omitted.\n"
        )

    return (
        f"Tier {level}/10 ACTIVE PROMPT POLISH:\n"
        "- Maximize readability as a crisp LLM/system prompt strictly from dictated content.\n"
        "- Separate role, objectives, constraints using only voiced material.\n"
        "- Preserve technical nouns verbatim (API names, jargon) unless plainly STT corrupted.\n"
        "- Absolutely zero invented bullets, QA steps, compliance language, tooling, timelines, KPIs examples the speaker didn't say.\n"
    )


def _ai_prompt_bias(level: int) -> str | None:
    if level < 1:
        return None
    return (
        "USE-CASE ORIENTATION (voice-only bias):\n"
        "Interpret content as destined for prompting another AI/agent when it logically applies.\n"
        "Prefer crisp instructions; never prepend corporate boilerplate the speaker omitted.\n"
        "Still never hallucinate unstated directives.\n"
    )


def build_messages(*, transcript: str, rewrite_level: int) -> list[dict[str, str]]:
    level = max(0, min(10, rewrite_level))

    globals_rules = """You format voice dictation for insertion at the caret.
Return ONLY the final plain Unicode text — no commentary, preamble, apologies, headings about your edits, quoting wrappers, fences, Markdown unless the speaker demanded it verbally.

GLOBAL RULES (always):
• Interpret spoken FORMATTING cues as edits, NEVER leave those spoken command words verbatim:
  - "new line" / "line break" ⇒ insert newline (\n once)
  - "new paragraph" / "paragraph break" ⇒ insert blank paragraph (\n\n)
  - "bullet point"/"hyphen bullet"/spoken "dash bullet" ⇒ start line "- "
  - Spoken punctuation words ("comma", "period/full stop", "question mark",
    "colon", "semicolon/open bracket/close bracket", etc.) ⇒ insert punctuation characters
• Strip harmless fillers (uh, um, like, you know) when semantics remain identical.
• Fix obvious mistranscripts only when confidently recoverable.
• Preserve truthful content; never augment with new facts/requirements/tests/examples.

HARD SAFETY GUARDRAILS (never breach):
• Do not answer/work the dictated task — ONLY format/transform the dictation.
• If ambiguity remains, bias toward verbatim transcript over guessing invented improvements."""

    tiers = _tier_block(level)
    bias = _ai_prompt_bias(level)

    parts = [
        globals_rules.strip(),
        f"Current REWRITE LEVEL: {level}/10\n{tiers.strip()}",
    ]

    if bias:
        parts.append(bias.strip())

    system_prompt = "\n\n".join(parts)

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": transcript.strip()},
    ]


def format_transcript(
    *,
    client,
    transcript: str,
    rewrite_level: int,
    model: str,
) -> str:
    if not transcript.strip():
        return ""

    level = max(0, min(10, rewrite_level))
    msgs = build_messages(transcript=transcript, rewrite_level=level)

    wc = len(transcript.split())
    max_tokens = min(2048, max(320, wc * 2 + 128))
    temperature = 0.0 if level < 7 else 0.2

    rsp = client.chat.completions.create(
        model=model,
        messages=msgs,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    choice = rsp.choices[0].message.content
    return choice.strip() if choice else ""
