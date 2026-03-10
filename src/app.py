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

from .tools import PYTHON_TOOL, run_python

load_dotenv()

deepseek_client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)

ollama_client = OpenAI(
    api_key="ollama",
    base_url="http://localhost:11434/v1",
)

DEEPSEEK_CHAT = "deepseek-chat"
DEEPSEEK_REASONER = "deepseek-reasoner"
OLLAMA_QWEN = "qwen3.5:35b-a3b"
ROUNDS = 10


@dataclass
class Fact:
    statement: str
    type: str = "fact"      # "fact" | "assumption" | "goal" | "definition"
    proof: str | None = None
    comment: str | None = None


STATEMENT_AGENT_SYSTEM = """\
You are a mathematical reasoning agent. Given a set of established statements:

1. First check if the ultimate goal can be derived from the established statements. If it is possible, derive the statement and the proof. 
2. If not, check if you can disprove the goal using the established statements. If it is possible, provide a proof to disprove the goal (i.e., a counterexample or a logical contradiction).
3. Otherwise, derive **one** new **interesting** mathematical statement or theorem, possibly using the established statements or definitions as premises or inspiration.
4. **Do not** think for too long or make big leaps in reasoning. 
5. Also provide a concise proof.
6. Format your response exactly as:
    statement:
    <statement>
    proof:
    <proof>
7. If you receive feedback from the checker, revise your statement in the same format.
8. Try not to repeat statements that have already been approved in previous rounds.
9. If you need to verify a numerical computation or check an example, use the run_python tool. Available packages: numpy, scipy, sympy, mpmath, z3-solver.
10. Use latex for mathematical expressions.
11. Do not add markdown formatting."""

GOAL_CHECK_SYSTEM = """\
1. You are a goal checker. 
Your only job is to check whether the goal is stated in any of the established statements.
2. **Do NOT** attempt to prove or disprove the goal yourself. 
3. **Be quick**. 
4. Respond with exactly one of:
    PROVEN: <which statement proves the goal>
    DISPROVEN: <which statement disproves the goal>
    NOT YET
"""

CHECKER_AGENT_SYSTEM = """\
You are a mathematical proof checker. For each statement-proof pair, verify:
1. The statement is correct and precisely stated.
2. The proof is valid: every step follows logically, no gaps or unjustified leaps.
3. If the proof is unclear, just ask for clarification. Do not try to solve it yourself.
4. Respond with exactly one of:
    APPROVED: <brief justification>
    statement:
    <restate the statement cleanly>
    proof:
    <restate the proof cleanly, improving clarity if possible>

    FIX NEEDED: <specific issue — state whether it is in the statement or the proof>
    CLARIFICATION NEEDED: <what is unclear and where>
5. If you need to verify a numerical computation or check an example, use the run_python tool. Available packages: numpy, scipy, sympy, mpmath, z3-solver.
6. Use latex for mathematical expressions.
7. Do not add markdown formatting."""


"""-----------------------------------------------------------------------------------------------
Agent interaction functions
-----------------------------------------------------------------------------------------------"""
_full_log: list[str] = []


def _stream(client: OpenAI, kwargs: dict) -> tuple[str, str, dict[int, dict]]:
    """Stream one response, printing CoT in real time. Returns (reasoning, content, tool_calls_map)."""
    reasoning, content = "", ""
    tool_calls_map: dict[int, dict] = {}
    reasoning_started = False
    for chunk in client.chat.completions.create(**kwargs, stream=True):
        delta = chunk.choices[0].delta
        if getattr(delta, "reasoning_content", None):
            if not reasoning_started:
                reasoning_started = True
            sys.stdout.write(delta.reasoning_content)
            sys.stdout.flush()
            reasoning += delta.reasoning_content
        if getattr(delta, "content", None):
            content += delta.content
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_map:
                    tool_calls_map[idx] = {"id": tc.id, "name": tc.function.name, "arguments": ""}
                if tc.function.arguments:
                    tool_calls_map[idx]["arguments"] += tc.function.arguments
    if reasoning_started:
        sys.stdout.write("\n")
        sys.stdout.flush()
        _full_log.append(f"[Thinking]\n{reasoning}")
    return reasoning, content, tool_calls_map


def chat(system: str, history: list[dict], client: OpenAI, model: str, tools: list | None = None) -> str:
    if model in ("deepseek-chat", "deepseek-reasoner", "MiniMax-M2"):
        messages = [{"role": "user", "content": system}, {"role": "assistant", "content": "Understood."}, *history]
    else:
        messages = [{"role": "system", "content": system}, *history]

    kwargs = {"model": model, "messages": messages, "temperature": 1}
    if tools:
        kwargs["tools"] = tools

    reasoning, content, tool_calls_map = _stream(client, kwargs)

    while tools and tool_calls_map:
        assistant_msg: dict = {"role": "assistant", "content": content}
        if reasoning and model in ("deepseek-reasoner", "MiniMax-M2"):
            assistant_msg["reasoning_content"] = reasoning
        assistant_msg["tool_calls"] = [
            {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": tc["arguments"]}}
            for tc in tool_calls_map.values()
        ]
        messages.append(assistant_msg)

        for tc in tool_calls_map.values():
            if tc["name"] == "run_python":
                code = json.loads(tc["arguments"])["code"]
                result = run_python(code)
                print(f"[Python] {code} → {result}")
                _full_log.append(f"[Python] {code}\n→ {result}")
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

        kwargs["messages"] = messages
        reasoning, content, tool_calls_map = _stream(client, kwargs)

    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()



"""-----------------------------------------------------------------------------------------------
Helper functions for parsing and managing statements, proofs, and logs.
-----------------------------------------------------------------------------------------------"""

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


def load_statements(input_path: Path, derived_path: Path) -> tuple[list[Fact], str | None]:
    if not input_path.exists():
        print(f"[red]Error: {input_path} not found.[/red]")
        sys.exit(1)
    goal = None
    facts: list[Fact] = []
    seen: set[str] = set()
    for entry in json.loads(input_path.read_text()):
        if entry["type"] == "goal":
            goal = entry["statement"]
        else:
            facts.append(Fact(statement=entry["statement"], type=entry["type"], proof=entry.get("proof"), comment=entry.get("comment")))
            seen.add(entry["statement"])
    if derived_path.exists():
        for entry in json.loads(derived_path.read_text()):
            if entry["type"] != "goal" and entry["statement"] not in seen:
                facts.append(Fact(statement=entry["statement"], type=entry["type"], proof=entry.get("proof"), comment=entry.get("comment")))
                seen.add(entry["statement"])
    return facts, goal


def save_facts(derived_path: Path, new_facts: list[Fact]) -> None:
    data: list[dict] = json.loads(derived_path.read_text()) if derived_path.exists() else []
    for fact in new_facts:
        entry = {"type": fact.type, "statement": fact.statement, "proof": fact.proof}
        if fact.comment:
            entry["comment"] = fact.comment
        data.append(entry)
    derived_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_log(log_path: Path, entries: list[str]) -> None:
    with open(log_path, "a") as f:
        for entry in entries:
            f.write(entry + "\n\n")


def print_facts(facts: list[Fact]) -> None:
    print("Current statements:")
    for idx, fact in enumerate(facts, start=1):
        print(f"[bold cyan]{idx}. {fact.statement}[/bold cyan]")
        if fact.comment:
            print(f"Comment: {fact.comment}")
    print()


"""-----------------------------------------------------------------------------------------------
Main loop of the proof assistant.
-----------------------------------------------------------------------------------------------"""
def run(json_path: Path) -> None:
    derived_path = json_path.parent / (json_path.stem + "_statements.json")
    log_path = json_path.parent / (json_path.stem + "_log.txt")
    full_log_path = json_path.parent / (json_path.stem + "_full_log.txt")
    if not derived_path.exists():
        derived_path.write_text(json_path.read_text(), encoding="utf-8")
    facts, goal = load_statements(json_path, derived_path)

    log: list[str] = []
    log_offset = 0

    timestamp = f"\n=== Run {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n"
    with open(log_path, "a") as f:
        f.write(timestamp)
    with open(full_log_path, "a", encoding="utf-8") as f:
        f.write(timestamp)

    def log_print(msg: str, label: str = "") -> None:
        print(msg)
        plain = re.sub(r"\[.*?\]", "", msg).strip()
        log.append((label + " " + plain).strip() if label else plain)
        _full_log.append(plain)

    print(f"\n[bold]=== {json_path} | Round starting ===\n[/bold]")
    if goal:
        print(f"[bold yellow]Goal: {goal}[/bold yellow]\n")
    print_facts(facts)

    stmt_history: list[dict] = []
    check_history: list[dict] = []
    new_facts: list[Fact] = []
    def check_goal() -> str:
        context = "Established statements:\n" + "\n".join(f"- {f.statement}" for f in facts)
        result = chat(GOAL_CHECK_SYSTEM, [{"role": "user", "content": f"{context}\n\nGoal: {goal}\n\nHas the goal been proven or disproven?"}], deepseek_client, DEEPSEEK_REASONER, tools=[PYTHON_TOOL])
        log_print(f"[bold magenta][Goal check] {result}[/bold magenta]\n", "[Goal check]")
        upper = result.upper()
        if upper.startswith("PROVEN"):
            return "PROVEN"
        if upper.startswith("DISPROVEN"):
            return "DISPROVEN"
        return "NOT YET"

    def run_checker(prompt: str) -> str:
        check_history.append({"role": "user", "content": prompt})
        verdict = chat(CHECKER_AGENT_SYSTEM, check_history, deepseek_client, DEEPSEEK_REASONER, tools=[PYTHON_TOOL])
        check_history.append({"role": "assistant", "content": verdict})
        log_print(f"[bold blue][Checker]  {verdict}[/bold blue]\n", "[Checker]")
        return verdict

    def handle_approved(verdict: str, approval_msg: str) -> str:
        fact = parse_statement_proof(verdict)
        if fact:
            fact.comment = "Derived"
            facts.append(fact)
            new_facts.append(fact)
        stmt_history.append({"role": "user", "content": approval_msg})
        stmt_history.append({"role": "assistant", "content": "Understood."})
        return check_goal() if goal else "NOT YET"

    goal_outcome = "NOT YET"
    for round_num in range(1, ROUNDS + 1):
        log_print(f"--- Round {round_num} ---")
        print_facts(facts)

        user_hint = input("Hint (or Enter to skip): ").strip()

        context = "Established statements:\n" + "\n".join(f"- {f.statement}" for f in facts)
        goal_hint = f"\n\nUltimate goal to work towards: {goal}" if goal else ""
        hint_str = f"\n\nHint from user: {user_hint}" if user_hint else ""
        stmt_history.append({"role": "user", "content": context + goal_hint + hint_str + "\n\nDerive one new mathematical statement."})
        claim = chat(STATEMENT_AGENT_SYSTEM, stmt_history, deepseek_client, DEEPSEEK_REASONER, tools=[PYTHON_TOOL])
        stmt_history.append({"role": "assistant", "content": claim})
        log_print(f"[bold green][Proposer] {claim}[/bold green]\n", "[Proposer]")

        verdict = run_checker(f"{context}\n\nReview this new statement and its proof:\n\n{claim}")

        if verdict.upper().startswith("APPROVED"):
            goal_outcome = handle_approved(verdict, "Your statement was approved.")
        else:
            stmt_history.append({"role": "user", "content": f"Checker feedback: {verdict}\n\nRevise your statement."})
            claim = chat(STATEMENT_AGENT_SYSTEM, stmt_history, deepseek_client, DEEPSEEK_REASONER, tools=[PYTHON_TOOL])
            stmt_history.append({"role": "assistant", "content": claim})
            log_print(f"[bold yellow][Proposer] (revised) {claim}[/bold yellow]\n", "[Proposer revised]")

            verdict = run_checker(f"{context}\n\nReview this revised statement and its proof:\n\n{claim}")

            if verdict.upper().startswith("APPROVED"):
                goal_outcome = handle_approved(verdict, "Your revised statement was approved.")
            else:
                stmt_history.append({"role": "user", "content": f"Your revised statement was also rejected: {verdict}. Keep this in mind for the next round."})
                stmt_history.append({"role": "assistant", "content": "Understood."})
                goal_outcome = "NOT YET"

        if new_facts:
            save_facts(derived_path, new_facts)
            new_facts.clear()
        append_log(log_path, log[log_offset:])
        log_offset = len(log)
        with open(full_log_path, "a", encoding="utf-8") as f:
            for entry in _full_log:
                f.write(entry + "\n\n")
        _full_log.clear()

        if goal_outcome == "PROVEN":
            print("\n[bold green]=== Goal proven! ===[/bold green]")
            break
        if goal_outcome == "DISPROVEN":
            print("\n[bold red]=== Goal disproven! ===[/bold red]")
            break

    print(f"\n[dim]Statements and log saved to {json_path.parent}[/dim]")


