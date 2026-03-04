from asyncio import log
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from rich import print
from rich.console import Console
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# API client for the Proposer agent (DeepSeek chat model)
deepseek_client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)

# API client for the Checker agent (MiniMax reasoning model)
minimax_client = OpenAI(
    api_key=os.environ["MINIMAX_API_KEY"],
    base_url="https://api.minimax.io/v1",
)

DEEPSEEK_CHAT = "deepseek-chat"  # Proposer: derives new mathematical statements
DEEPSEEK_REASONER = "deepseek-reasoner"  # Proposer: derives new mathematical statements
MINIMAX_MODEL = "MiniMax-M2.5"    # Checker: verifies correctness and rigor
ROUNDS = 10                        # Number of propose-check cycles per run

OUTPUTS_DIR = Path("outputs")

# System prompt for the Proposer: instructs it to derive one new statement with proof per round
STATEMENT_AGENT_SYSTEM = """\
You are a mathematical reasoning agent. Given a set of established statements:
1. Derive **one** new interesting mathematical statement or theorem that follows from them.
2. The new statement should be **easy** to derive from the existing ones (few justification steps).
3. **Do not try to derive statements that are too far** away from the existing ones.
4. Also provide a concise proof. 
5. **Do not** think for too long.
6. Format your response exactly as:
statement:
<statement>
proof:
<proof>
If you receive feedback from the checker, revise your statement in the same format.
Try not to repeat statements that have already been approved in previous rounds.
Do not add markdown formatting."""

GOAL_CHECK_SYSTEM = """\
You are a goal checker. Your only job is to check whether the goal appears as one of the established statements (verbatim or clearly equivalent).
Do NOT attempt to prove the goal yourself. Do NOT reason about whether it could be derived.
Simply check: is the goal already an established statement?
Respond with exactly one of:
  PROVEN: <which statement matches the goal>
  NOT YET
Do not add markdown formatting."""

# System prompt for the Checker: instructs it to approve or flag issues
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
Do not add markdown formatting."""


def chat(system: str, history: list[dict], client: OpenAI, model: str) -> str:
    # deepseek-chat and deepseek-reasoner do not support the system role; inject it as a user/assistant prefix instead
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
                    print("[dim][Thinking][/dim]")
                    reasoning_started = True
                print(f"[dim]{delta.reasoning_content}[/dim]", end="", flush=True)
            if getattr(delta, "content", None):
                answer += delta.content
        if reasoning_started:
            print()
        return answer.strip()

    response = client.chat.completions.create(model=model, messages=messages)
    text = response.choices[0].message.content.strip()
    # MiniMax M2.5 puts chain-of-thought inline as <think>...</think>; strip it so verdict parsing works
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return text


def parse_statement(text: str) -> str | None:
    # Text is formatted as "statement:\n<stmt>\nproof:\n<proof>"
    # Use rfind to pick the LAST statement/proof block in case the Proposer self-corrects mid-response
    lower = text.lower()
    s_start = lower.rfind("statement:")
    p_start = lower.rfind("proof:")
    if s_start == -1 or p_start == -1 or p_start < s_start:
        return None
    return text[s_start + len("statement:"):p_start].strip()


def parse_proof(text: str) -> str | None:
    # Text is formatted as "statement:\n<stmt>\nproof:\n<proof>"
    # Use rfind to pick the LAST statement/proof block in case the Proposer self-corrects mid-response
    lower = text.lower()
    s_start = lower.rfind("statement:")
    p_start = lower.rfind("proof:")
    if s_start == -1 or p_start == -1 or p_start < s_start:
        return None
    return text[p_start + len("proof:"):].strip()


def load_statements(chat_id: str) -> tuple[list[str], str | None]:
    path = OUTPUTS_DIR / f"statements_{chat_id}.txt"
    if not path.exists():
        print(f"[red]Error: {path} not found. Create it with seed statements before the first run.[/red]")
        sys.exit(1)
    goal = None
    facts = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("goal:"):
            goal = line[len("goal:"):].strip()
        elif line.lower().startswith("proof:"):
            pass  # skip proof lines; they are stored for reference but not fed as facts
        else:
            facts.append(re.sub(r"^\d+\.\s*", "", line))
    return facts, goal


def append_statements(chat_id: str, new_statements: list[tuple[str, str]]) -> None:
    path = OUTPUTS_DIR / f"statements_{chat_id}.txt"
    # Count only statement lines (not proof lines or blank lines) for numbering
    existing_count = sum(
        1 for l in path.read_text().splitlines()
        if l.strip() and not l.strip().lower().startswith("proof:") and not l.strip().lower().startswith("goal:")
    )
    with open(path, "a") as f:
        for i, (s, proof) in enumerate(new_statements, start=existing_count + 1):
            f.write(f"\n{i}. {s}\nProof: {proof}\n")


def append_log(chat_id: str, entries: list[str]) -> None:
    path = OUTPUTS_DIR / f"log_{chat_id}.txt"
    with open(path, "a") as f:
        for entry in entries:
            f.write(entry + "\n")


def fact_print(facts: list[str]) -> None:
    print("Current statements:")
    for idx, f in enumerate(facts, start=1):
        print(f"[bold cyan]{idx}. {f}[/bold cyan]")
    print()


def run(chat_id: str) -> None:
    facts, goal = load_statements(chat_id)  # all known facts, grows as statements are approved

    log: list[str] = []                   # collects all agent exchanges for log_id.txt
    log_offset = 0                         # index up to which log entries have been flushed

    def log_print(msg: str, label: str = "") -> None:
        """Print to console (with Rich markup) and append plain text to log."""
        print(msg)
        plain = re.sub(r"\[.*?\]", "", msg).strip()  # strip Rich tags for the log file
        log.append((label + " " + plain).strip() if label else plain)

    # Write run header to log file once
    log_path = OUTPUTS_DIR / f"log_{chat_id}.txt"
    with open(log_path, "a") as f:
        f.write(f"\n=== Run {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")

    print(f"\n[bold]=== Chat: {chat_id} | Round starting ===\n[/bold]")
    if goal:
        print(f"[bold yellow]Goal: {goal}[/bold yellow]\n")
    print("Current statements:")
    for f in facts:
        print(f"  {f}")
    print()

    stmt_history: list[dict] = []   # Proposer's conversation history (its own context)
    check_history: list[dict] = []  # Checker's conversation history (its own context)
    new_statements: list[str] = []  # statements approved during this run, to append to file
    goal_proven = False

    def check_goal(facts: list[str]) -> bool:
        """Ask the Checker whether the accumulated facts are sufficient to prove the goal."""
        context = "Established statements:\n" + "\n".join(f"- {s}" for s in facts)
        prompt = f"{context}\n\nGoal: {goal}\n\nWas the goal reached?"
        result = chat(GOAL_CHECK_SYSTEM, [{"role": "user", "content": prompt}], deepseek_client, DEEPSEEK_REASONER)
        log_print(f"[bold magenta][Goal check] {result}[/bold magenta]\n", "[Goal check]")
        return result.upper().startswith("PROVEN")

    for round_num in range(1, ROUNDS + 1):
        log_print(f"--- Round {round_num} ---")

        # Build context from all current facts and ask the Proposer for a new statement
        context = "Established statements:\n" + "\n".join(f"- {s}" for s in facts)
        goal_hint = f"\n\nUltimate goal to work towards: {goal}" if goal else ""
        stmt_history.append({"role": "user", "content": context + goal_hint + "\n\nDerive one new mathematical statement."})
        claim = chat(STATEMENT_AGENT_SYSTEM, stmt_history, deepseek_client, DEEPSEEK_CHAT)
        stmt_history.append({"role": "assistant", "content": claim})
        log_print(f"[bold green][Proposer] {claim}[/bold green]\n", "[Proposer]")

        # Send the claim to the Checker for review, including established facts so proofs can reference them
        check_history.append({"role": "user", "content": f"{context}\n\nReview this new statement and its proof:\n\n{claim}"})
        verdict = chat(CHECKER_AGENT_SYSTEM, check_history, deepseek_client, DEEPSEEK_REASONER)  # APPROVED / FIX NEEDED / CLARIFICATION NEEDED
        check_history.append({"role": "assistant", "content": verdict})
        log_print(f"[bold blue][Checker]  {verdict}[/bold blue]\n", "[Checker]")

        if verdict.upper().startswith("APPROVED"):
            statement = parse_statement(verdict)
            proof = parse_proof(verdict)
            if statement and proof:
                facts.append(statement)
                new_statements.append((statement, proof))
            stmt_history.append({"role": "user", "content": "Your statement was approved."})
            stmt_history.append({"role": "assistant", "content": "Understood."})
            if goal and check_goal(facts):
                goal_proven = True
        else:
            # Proposer revises based on the Checker's feedback
            stmt_history.append({"role": "user", "content": f"Checker feedback: {verdict}\n\nRevise your statement."})
            claim = chat(STATEMENT_AGENT_SYSTEM, stmt_history, deepseek_client, DEEPSEEK_CHAT)
            stmt_history.append({"role": "assistant", "content": claim})
            log_print(f"[bold yellow][Proposer] (revised) {claim}[/bold yellow]\n", "[Proposer revised]")

            # Checker gives a final verdict on the revision
            check_history.append({"role": "user", "content": f"{context}\n\nReview this revised statement and its proof:\n\n{claim}"})
            verdict = chat(CHECKER_AGENT_SYSTEM, check_history, deepseek_client, DEEPSEEK_REASONER)
            check_history.append({"role": "assistant", "content": verdict})
            log_print(f"[bold blue][Checker]  {verdict}[/bold blue]\n", "[Checker]")

            if verdict.upper().startswith("APPROVED"):
                statement = parse_statement(verdict)
                proof = parse_proof(verdict)
                if statement and proof:
                    facts.append(statement)
                    new_statements.append((statement, proof))
                stmt_history.append({"role": "user", "content": "Your revised statement was approved."})
                stmt_history.append({"role": "assistant", "content": "Understood."})
                if goal and check_goal(facts):
                    goal_proven = True
            else:
                # Inform the proposer that even the revision was rejected, so it can do better next round
                stmt_history.append({"role": "user", "content": f"Your revised statement was also rejected: {verdict}. Keep this in mind for the next round."})
                stmt_history.append({"role": "assistant", "content": "Understood."})

        # Flush new log entries and any newly approved statements after each round
        if new_statements:
            append_statements(chat_id, new_statements)
            new_statements.clear()
        append_log(chat_id, log[log_offset:])
        log_offset = len(log)

        # Print out current statements after each round
        fact_print(facts)

        if goal_proven:
            break

    # Summary
    if goal_proven:
        print(f"\n[bold green]=== Goal proven! ===[/bold green]")
    print(f"\n[dim]Statements and log saved to outputs/{chat_id}[/dim]")


if __name__ == "__main__":
    OUTPUTS_DIR.mkdir(exist_ok=True)
    chat_id = input("Chat ID: ").strip()
    if not chat_id:
        print("[red]Chat ID cannot be empty.[/red]")
        sys.exit(1)
    run(chat_id)
