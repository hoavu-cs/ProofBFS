"""Simplifier: takes a completed *_statements.txt and produces a simpler proof."""

import os
import re
import sys

from pathlib import Path

from rich import print
from openai import OpenAI
from dotenv import load_dotenv

from .txt_io import parse_txt
from .app import (
    DEEPSEEK_REASONER, GEMINI_PRO,
    GPT_4O, OR_GPT5,
    deepseek_client, gemini_client, openai_client, openrouter_client,
    _stream,
)

load_dotenv()

SIMPLIFY_ROUNDS = 3

GOAL_CHECK_SYSTEM = """\
You are a goal checker. You will be given a list of statements and a goal.
Your only job: determine whether the goal has been proven by examining whether
any statement directly states or clearly implies the goal.
Respond with exactly one of:
    PROVEN: <which statement proves the goal>
    NOT PROVEN"""

PROPOSER_SYSTEM = """\
You are a mathematical proof simplifier. You will be given:
- A goal (theorem to prove)
- Setup: definitions and given facts/assumptions
- A working proof: a sequence of derived statements that proves the goal

Your task: produce a **simpler, more direct** proof of the same goal.
Rules:
1. The proof must be correct and complete — every step must follow logically.
2. Aim to reduce the number of steps and eliminate unnecessary intermediate results.
3. Prefer elementary arguments over heavy machinery when possible.
4. Format your response exactly as:
    proof:
    <step-by-step proof, one claim per line, each followed by its justification>
5. Use LaTeX for mathematical expressions. No markdown formatting."""

VERIFIER_SYSTEM = """\
You are a mathematical proof verifier and judge of simplicity. You will be given:
- A goal
- Setup: definitions and given facts/assumptions
- The original proof (for reference)
- A proposed simplified proof

Your task: verify the proposed proof and assess whether it is simpler.
Rules:
1. Check every step is logically valid — no gaps or unjustified leaps.
2. A proof is simpler if it is shorter, more direct, or easier to follow.
3. Respond with exactly one of:
    APPROVED: <brief justification of correctness and simplicity>
    REJECTED: <specific issue — correctness problem or not actually simpler>"""


def _client(model: str) -> OpenAI:
    if model == GEMINI_PRO:
        return gemini_client
    if model in (GPT_4O,):
        return openai_client
    if model == OR_GPT5:
        return openrouter_client
    return deepseek_client


def _chat(system: str, history: list[dict], client: OpenAI, model: str, temperature: float = 1.0) -> str:
    if model == DEEPSEEK_REASONER:
        messages = [{"role": "user", "content": system}, {"role": "assistant", "content": "Understood."}, *history]
    else:
        messages = [{"role": "system", "content": system}, *history]
    kwargs = {"model": model, "messages": messages, "temperature": temperature}
    _, content, _ = _stream(client, kwargs)
    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()


def _format_context(goal: dict | None, definitions: list[dict], given_facts: list[dict]) -> str:
    parts: list[str] = []
    if goal:
        parts.append(f"Goal: {goal['statement']}")
    if definitions:
        parts.append("Definitions:\n" + "\n".join(f"- {d['statement']}" for d in definitions))
    if given_facts:
        parts.append("Given:\n" + "\n".join(f"- {f['statement']}" for f in given_facts))
    return "\n\n".join(parts)


def _format_derived(derived: list[dict]) -> str:
    lines = []
    for i, e in enumerate(derived, start=1):
        lines.append(f"Step {i}. {e['statement']}")
        if e.get("proof"):
            lines.append(f"   Proof: {e['proof']}")
    return "\n".join(lines)


def simplify(
    statements_path: Path,
    output_path: Path,
    proposer_model: str = DEEPSEEK_REASONER,
    verifier_model: str = DEEPSEEK_REASONER,
    rounds: int = SIMPLIFY_ROUNDS,
    temperature: float = 1.0,
) -> None:
    entries, goal, _ = parse_txt(statements_path)

    definitions: list[dict] = []
    given_facts: list[dict] = []
    derived: list[dict] = []

    for entry in entries:
        t = entry.get("type", "fact").lower()
        if entry.get("comment") == "Derived":
            derived.append(entry)
        elif t == "definition":
            definitions.append(entry)
        else:
            given_facts.append(entry)

    # Check goal has been proven
    if not goal:
        print("[red]No goal found in the statements file.[/red]")
        sys.exit(1)

    p_client = _client(proposer_model)
    v_client = _client(verifier_model)

    all_statements = "\n".join(f"- {e['statement']}" for e in entries)
    goal_check_prompt = f"Goal: {goal['statement']}\n\nStatements:\n{all_statements}\n\nHas the goal been proven?"
    verdict = _chat(GOAL_CHECK_SYSTEM, [{"role": "user", "content": goal_check_prompt}], v_client, verifier_model, temperature=0)
    print(f"[bold magenta][Goal check] {verdict}[/bold magenta]\n")
    if "PROVEN" not in verdict.upper():
        print("[red]Goal has not been proven in this file. Exiting.[/red]")
        sys.exit(0)

    context = _format_context(goal, definitions, given_facts)
    original_proof = _format_derived(derived)

    print(f"[bold]Original proof has {len(derived)} steps.[/bold]\n")

    best_proof: str | None = None

    for round_num in range(1, rounds + 1):
        print(f"[bold]=== Simplification round {round_num}/{rounds} ===[/bold]")

        prior = f"\n\nPrevious simplified proof (improve on this):\n{best_proof}" if best_proof else ""
        propose_prompt = (
            f"{context}\n\n"
            f"Original proof:\n{original_proof}"
            f"{prior}\n\n"
            "Propose a simpler proof of the goal."
        )
        proposed = _chat(PROPOSER_SYSTEM, [{"role": "user", "content": propose_prompt}], p_client, proposer_model, temperature=temperature)
        print(f"[bold green][Proposer]\n{proposed}[/bold green]\n")

        verify_prompt = (
            f"{context}\n\n"
            f"Original proof:\n{original_proof}\n\n"
            f"Proposed simplified proof:\n{proposed}"
        )
        result = _chat(VERIFIER_SYSTEM, [{"role": "user", "content": verify_prompt}], v_client, verifier_model, temperature=temperature)
        print(f"[bold blue][Verifier] {result}[/bold blue]\n")

        if "APPROVED" in result.upper():
            best_proof = proposed
            print(f"[bold green]Proof accepted in round {round_num}.[/bold green]\n")
        else:
            print(f"[yellow]Proof rejected in round {round_num}, continuing...[/yellow]\n")

    if best_proof:
        _write_txt(output_path, goal, definitions, given_facts, best_proof)
        _write_latex(output_path.with_suffix(".tex"), goal, definitions, given_facts, best_proof)
    else:
        print("[yellow]No simplified proof was approved after all rounds.[/yellow]")


def _write_txt(output_path: Path, goal: dict, definitions: list[dict], given_facts: list[dict], proof: str) -> None:
    lines: list[str] = []
    lines.append(f"Theorem: {goal['statement']}\n")
    if definitions:
        lines.append("Definitions:")
        for d in definitions:
            lines.append(f"  - {d['statement']}")
        lines.append("")
    if given_facts:
        lines.append("Given:")
        for f in given_facts:
            lines.append(f"  - {f['statement']}")
        lines.append("")
    lines.append("Proof:")
    lines.append(proof)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[bold green]Simplified proof written to {output_path}[/bold green]")


def _write_latex(output_path: Path, goal: dict, definitions: list[dict], given_facts: list[dict], proof: str) -> None:
    lines: list[str] = [
        r"\documentclass{article}",
        r"\usepackage{amsmath, amssymb, amsthm}",
        r"\newtheorem{theorem}{Theorem}",
        r"\newtheorem{definition}{Definition}",
        r"\newtheorem{assumption}{Assumption}",
        r"\begin{document}",
        "",
    ]

    if definitions:
        lines.append(r"\section*{Definitions}")
        for d in definitions:
            lines += [r"\begin{definition}", d["statement"], r"\end{definition}", ""]

    if given_facts:
        lines.append(r"\section*{Given}")
        for f in given_facts:
            lines += [r"\begin{assumption}", f["statement"], r"\end{assumption}", ""]

    lines += [
        r"\section*{Main Result}",
        r"\begin{theorem}",
        goal["statement"],
        r"\end{theorem}",
        "",
        r"\begin{proof}",
        proof,
        r"\end{proof}",
        "",
        r"\end{document}",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[bold green]LaTeX written to {output_path}[/bold green]")
