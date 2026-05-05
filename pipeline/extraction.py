from __future__ import annotations

import re
from dataclasses import dataclass


CLAUSE_HEADER_PATTERN = re.compile(r"^\s*(\d+)\.\s+(.+?)\s*$")


@dataclass
class ParsedClause:
    clause_number: str
    clause_title: str
    clause_text: str
    word_count: int


@dataclass
class ParsedContract:
    preamble: str
    clauses: list[ParsedClause]


def extract_clauses(contract_text: str) -> ParsedContract:
    lines = contract_text.splitlines()
    preamble_lines: list[str] = []
    clauses: list[ParsedClause] = []
    current_number: str | None = None
    current_title: str | None = None
    current_body_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current_number, current_title, current_body_lines
        if current_number is None or current_title is None:
            return
        clause_text = "\n".join(line.rstrip() for line in current_body_lines).strip()
        word_count = len(clause_text.split())
        clauses.append(
            ParsedClause(
                clause_number=current_number,
                clause_title=current_title,
                clause_text=clause_text,
                word_count=word_count,
            )
        )
        current_number = None
        current_title = None
        current_body_lines = []

    for line in lines:
        match = CLAUSE_HEADER_PATTERN.match(line)
        if match:
            flush_current()
            current_number = match.group(1)
            current_title = match.group(2).strip()
            continue
        if current_number is None:
            preamble_lines.append(line.rstrip())
        else:
            current_body_lines.append(line.rstrip())

    flush_current()
    if not clauses:
        raise ValueError("No numbered clauses found in contract.txt.")

    preamble = "\n".join(preamble_lines).strip()
    return ParsedContract(preamble=preamble, clauses=clauses)
