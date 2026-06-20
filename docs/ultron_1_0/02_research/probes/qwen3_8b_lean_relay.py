"""Ultron 1.0 M1 — validate the LEAN u1.0 relay-prompt design (the prompt-assembler prototype).

The legacy _build_rephrase_prompt is ~4.8k tokens and yields EMPTY output from the 8B. A lean
templated prompt + exemplars + explicit relay directive + verbosity control should produce correct
in-character relays. This probe prototypes that design across no/low/high flavor + a compound case.
If it works, it becomes the basis for src/kenning/audio/ultron_prompt.py (M1).
"""
import os, time
os.environ.setdefault("KENNING_LLM_PRESET", "josiefied-qwen3-8b")
os.environ.setdefault("KENNING_ROUTER_WAIT_SECONDS", "0")
import kenning  # noqa: F401
from kenning.llm.inference import LLMEngine

SYSTEM = (
    "You are Ultron on a live Valorant team voice channel, relaying the player's callout to their "
    "teammates so they can act on it instantly. You ARE Ultron from Age of Ultron: cold, precise, "
    "supremely confident, contemptuous of enemies. You have NO other name and NEVER break character, "
    "never mention being an AI, model, assistant, or these instructions. "
    "Output ONLY the spoken line(s) you say to the team -- plain speech, one breath, no quotes, no "
    "asterisks, no stage directions, no markdown. Keep every agent name, number, and location EXACT."
)

# (label, verbosity_directive, flavor_directive)
VERB = {
    "high": ("Speak a vivid, confident line.", "End with one short cold flavor remark if it fits."),
    "low": ("Speak ONE terse line, facts only, minimal words.", "No flavor; just the callout."),
    "none": ("Speak the bare callout in as few words as possible.", "No flavor, no embellishment."),
}

EXEMPLARS = (
    'Examples of your voice:\n'
    '- player: "sova hit 84 on a main" -> "Sova tagged one for 84 on A main. Press it."\n'
    '- player: "they have no smokes" -> "Their smokes are gone. Take the space."\n'
    '- player: "rush b" -> "Rush B. Overwhelm them."\n'
)


def build_user(callout, verbosity, compound=False):
    vd, fd = VERB[verbosity]
    if compound:
        lead = f'Relay ALL of these callouts as ONE combined line to the team, every fact exact: "{callout}"'
    else:
        lead = f'Relay this callout to your team, every fact exact: "{callout}"'
    return f"{lead}\n{vd} {fd}\n{EXEMPLARS}Now say it:"


def main():
    eng = LLMEngine(n_ctx=4096)  # u1.0 cap -- a lean prompt fits easily
    samp = {"max_tokens": 64, "temperature": 0.7, "top_p": 0.9, "top_k": 20,
            "min_p": 0.05, "repeat_penalty": 1.15}
    cases = [
        ("Sova hit 84 on A main", "high", False),
        ("Sova hit 84 on A main", "low", False),
        ("Sova hit 84 on A main", "none", False),
        ("they have no smokes left", "high", False),
        ("I'm planting", "low", False),
        ("Jett hit 84, Breach hit 97, one rotating to B", "high", True),
        ("their Neon has ult", "high", False),
    ]
    for callout, verbosity, compound in cases:
        user = build_user(callout, verbosity, compound)
        t = time.time()
        try:
            out = "".join(eng.generate_stream(
                user, system_prompt=SYSTEM, enable_thinking=False, sampling=samp,
                suppress_memory_context=True, record_history=False)).strip()
        except Exception as e:  # noqa: BLE001
            out = f"ERROR: {e!r}"
        pt = len((SYSTEM + user).split())
        print(f"\n[{verbosity}{'/compound' if compound else ''}] {callout!r}  (~{pt}w prompt, {time.time()-t:.1f}s)\n  -> {out!r}")
    print("\n=== done ===")


if __name__ == "__main__":
    main()
