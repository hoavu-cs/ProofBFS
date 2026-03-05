import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rich import print
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

deepseek_client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)

DEEPSEEK_CHAT = "deepseek-chat"
DEEPSEEK_REASONER = "deepseek-reasoner"
ROUNDS = 10

OUTPUTS_DIR = Path("outputs")


@dataclass
class Fact:
    statement: str
    type: str = "fact"      # "fact" | "assumption" | "goal"
    proof: str | None = None


STATEMENT_AGENT_SYSTEM = """\
You are a mathematical reasoning agent. Given a set of established statements:
1. Derive **one** new **interesting** mathematical statement or theorem, possibly using the established statements as premises or inspiration.
2. **Do not try to derive statements that are too far** away from the existing ones.
3. Also provide a concise proof.
4. **Do not** think for too long.
5. Format your response exactly as:
statement:
<statement>
proof:
<proof>
If you receive feedback from the checker, revise your statement in the same format.
Try not to repeat statements that have already been approved in previous rounds.
Use LaTeX for all mathematical notation (e.g. $x \\geq 0$). Do not use Unicode symbols (≥, ∈, →, etc.).
Do not add markdown formatting."""

GOAL_CHECK_SYSTEM = """\
You are a goal checker. Your only job is to check whether the goal appears as one of the established statements (verbatim or clearly equivalent).
Do NOT attempt to prove the goal yourself. Do NOT reason about whether it could be derived.
Simply check: is the goal already an established statement?
Respond with exactly one of:
  PROVEN: <which statement matches the goal>
  NOT YET
Use LaTeX for all mathematical notation. Do not add markdown formatting."""

CHECKER_AGENT_SYSTEM = """\
You are a mathematical proof checker. For each statement-proof pair, verify:
1. The statement is correct and precisely stated.
2. The proof is valid: every step follows logically, no gaps or unjustified leaps.
3. If the proof is unclear, just ask for clarification. Do not try to solve it yourself.
Respond with exactly one of:
  APPROVED: <brief justification>
  statement:
  <restate the statement cleanly>
  proof:
  <restate the proof cleanly, improving clarity if possible>

  FIX NEEDED: <specific issue — state whether it is in the statement or the proof>
  CLARIFICATION NEEDED: <what is unclear and where>
Use LaTeX for all mathematical notation (e.g. $x \\geq 0$). Do not use Unicode symbols (≥, ∈, →, etc.).
Do not add markdown formatting."""


def chat(system: str, history: list[dict], client: OpenAI, model: str) -> str:
    if model in ("deepseek-chat", "deepseek-reasoner"):
        messages = [{"role": "user", "content": system}, {"role": "assistant", "content": "Understood."}, *history]
    else:
        messages = [{"role": "system", "content": system}, *history]

    if model == "deepseek-reasoner":
        response = client.chat.completions.create(model=model, messages=messages, stream=True)
        answer = ""
        reasoning_started = False
        for chunk in response:
            delta = chunk.choices[0].delta
            if getattr(delta, "reasoning_content", None):
                if not reasoning_started:
                    print("[Thinking]")
                    reasoning_started = True
                print(delta.reasoning_content, end="", flush=True)
            if getattr(delta, "content", None):
                answer += delta.content
        if reasoning_started:
            print()
        return answer.strip()

    response = client.chat.completions.create(model=model, messages=messages)
    text = response.choices[0].message.content.strip()
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def parse_statement_proof(text: str) -> Fact | None:
    """Extract the last statement/proof block from a formatted LLM response."""
    lower = text.lower()
    s_start = lower.rfind("statement:")
    p_start = lower.rfind("proof:")
    if s_start == -1 or p_start == -1 or p_start < s_start:
        return None
    statement = text[s_start + len("statement:"):p_start].strip()
    proof = text[p_start + len("proof:"):].strip() or None
    return Fact(statement=statement, type="fact", proof=proof)


def load_statements(chat_id: str) -> tuple[list[Fact], str | None]:
    path = OUTPUTS_DIR / f"statements_{chat_id}.json"
    if not path.exists():
        print(f"[red]Error: {path} not found.[/red]")
        sys.exit(1)
    goal = None
    facts: list[Fact] = []
    for entry in json.loads(path.read_text()):
        if entry["type"] == "goal":
            goal = entry["statement"]
        else:
            facts.append(Fact(statement=entry["statement"], type=entry["type"], proof=entry.get("proof")))
    return facts, goal


def save_facts(chat_id: str, new_facts: list[Fact]) -> None:
    path = OUTPUTS_DIR / f"statements_{chat_id}.json"
    data: list[dict] = json.loads(path.read_text())
    for fact in new_facts:
        data.append({"type": fact.type, "statement": fact.statement, "proof": fact.proof})
    path.write_text(json.dumps(data, indent=2))


def append_log(chat_id: str, entries: list[str]) -> None:
    path = OUTPUTS_DIR / f"log_{chat_id}.txt"
    with open(path, "a") as f:
        for entry in entries:
            f.write(entry + "\n\n")


def print_facts(facts: list[Fact]) -> None:
    print("Current statements:")
    for idx, fact in enumerate(facts, start=1):
        print(f"[bold cyan]{idx}. {fact.statement}[/bold cyan]")
    print()


def run(chat_id: str) -> None:
    facts, goal = load_statements(chat_id)

    log: list[str] = []
    log_offset = 0

    def log_print(msg: str, label: str = "") -> None:
        print(msg)
        plain = re.sub(r"\[.*?\]", "", msg).strip()
        log.append((label + " " + plain).strip() if label else plain)

    log_path = OUTPUTS_DIR / f"log_{chat_id}.txt"
    with open(log_path, "a") as f:
        f.write(f"\n=== Run {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")

    print(f"\n[bold]=== Chat: {chat_id} | Round starting ===\n[/bold]")
    if goal:
        print(f"[bold yellow]Goal: {goal}[/bold yellow]\n")
    print_facts(facts)

    stmt_history: list[dict] = []
    check_history: list[dict] = []
    new_facts: list[Fact] = []
    goal_proven = False

    def check_goal() -> bool:
        context = "Established statements:\n" + "\n".join(f"- {f.statement}" for f in facts)
        result = chat(GOAL_CHECK_SYSTEM, [{"role": "user", "content": f"{context}\n\nGoal: {goal}\n\nWas the goal reached?"}], deepseek_client, DEEPSEEK_REASONER)
        log_print(f"[bold magenta][Goal check] {result}[/bold magenta]\n", "[Goal check]")
        return result.upper().startswith("PROVEN")

    def run_checker(prompt: str) -> str:
        check_history.append({"role": "user", "content": prompt})
        verdict = chat(CHECKER_AGENT_SYSTEM, check_history, deepseek_client, DEEPSEEK_REASONER)
        check_history.append({"role": "assistant", "content": verdict})
        log_print(f"[bold blue][Checker]  {verdict}[/bold blue]\n", "[Checker]")
        return verdict

    def handle_approved(verdict: str, claim: str, approval_msg: str) -> bool:
        fact = parse_statement_proof(verdict) or parse_statement_proof(claim)
        if fact:
            facts.append(fact)
            new_facts.append(fact)
        stmt_history.append({"role": "user", "content": approval_msg})
        stmt_history.append({"role": "assistant", "content": "Understood."})
        return bool(goal and check_goal())

    for round_num in range(1, ROUNDS + 1):
        log_print(f"--- Round {round_num} ---")

        context = "Established statements:\n" + "\n".join(f"- {f.statement}" for f in facts)
        goal_hint = f"\n\nUltimate goal to work towards: {goal}" if goal else ""
        stmt_history.append({"role": "user", "content": context + goal_hint + "\n\nDerive one new mathematical statement."})
        claim = chat(STATEMENT_AGENT_SYSTEM, stmt_history, deepseek_client, DEEPSEEK_REASONER)
        stmt_history.append({"role": "assistant", "content": claim})
        log_print(f"[bold green][Proposer] {claim}[/bold green]\n", "[Proposer]")

        verdict = run_checker(f"{context}\n\nReview this new statement and its proof:\n\n{claim}")

        if verdict.upper().startswith("APPROVED"):
            goal_proven = handle_approved(verdict, claim, "Your statement was approved.")
        else:
            stmt_history.append({"role": "user", "content": f"Checker feedback: {verdict}\n\nRevise your statement."})
            claim = chat(STATEMENT_AGENT_SYSTEM, stmt_history, deepseek_client, DEEPSEEK_REASONER)
            stmt_history.append({"role": "assistant", "content": claim})
            log_print(f"[bold yellow][Proposer] (revised) {claim}[/bold yellow]\n", "[Proposer revised]")

            verdict = run_checker(f"{context}\n\nReview this revised statement and its proof:\n\n{claim}")

            if verdict.upper().startswith("APPROVED"):
                goal_proven = handle_approved(verdict, claim, "Your revised statement was approved.")
            else:
                stmt_history.append({"role": "user", "content": f"Your revised statement was also rejected: {verdict}. Keep this in mind for the next round."})
                stmt_history.append({"role": "assistant", "content": "Understood."})

        if new_facts:
            save_facts(chat_id, new_facts)
            new_facts.clear()
        append_log(chat_id, log[log_offset:])
        log_offset = len(log)

        print_facts(facts)

        if goal_proven:
            break

    if goal_proven:
        print("\n[bold green]=== Goal proven! ===[/bold green]")
    print(f"\n[dim]Statements and log saved to outputs/{chat_id}[/dim]")


if __name__ == "__main__":
    OUTPUTS_DIR.mkdir(exist_ok=True)
    chat_id = input("Chat ID: ").strip()
    if not chat_id:
        print("[red]Chat ID cannot be empty.[/red]")
        sys.exit(1)
    run(chat_id)
