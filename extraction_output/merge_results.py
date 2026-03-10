#!/usr/bin/env python3
"""Мерж результатов извлечения словаря и правил из резюме в накопительный JSON."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# --init: создать accumulated_results.json с baseline из domain/rules.py
# ---------------------------------------------------------------------------
def cmd_init(output_path: Path) -> None:
    # Импортируем baseline из domain/rules.py
    domain_dir = str(Path(__file__).resolve().parent.parent)
    if domain_dir not in sys.path:
        sys.path.insert(0, domain_dir)

    from domain.rules import DOMAIN_VOCABULARY as domain_vocab, DOMAIN_RULES as domain_rules

    vocabulary = {}
    for name, desc in domain_vocab.items():
        vocabulary[name] = {
            "description": desc,
            "sources": [],
            "is_baseline": True,
        }

    rules = []
    for label, formula in domain_rules:
        rules.append({
            "label": label,
            "formula": formula,
            "sources": [],
            "is_baseline": True,
        })

    data = {
        "metadata": {
            "last_updated": _now_iso(),
            "total_processed": 0,
            "total_errors": 0,
        },
        "vocabulary": vocabulary,
        "rules": rules,
        "processed_files": {},
    }

    _save_json(output_path, data)
    print(f"Initialized {output_path} with {len(vocabulary)} vocab + {len(rules)} rules")


# ---------------------------------------------------------------------------
# --merge: принять JSON от Claude (stdin), добавить новые записи
# ---------------------------------------------------------------------------
def cmd_merge(output_path: Path, source: str) -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        print("ERROR: empty stdin", file=sys.stderr)
        sys.exit(1)

    try:
        claude_result = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON from Claude: {e}", file=sys.stderr)
        sys.exit(1)

    data = _load_json(output_path)

    new_vocab = claude_result.get("new_vocabulary", {})
    new_rules = claude_result.get("new_rules", [])
    claims_found = claude_result.get("claims_found", 0)

    vocab_added = 0
    rules_added = 0

    # Добавляем новые переменные (дедупликация по имени)
    for name, desc in new_vocab.items():
        if name not in data["vocabulary"]:
            data["vocabulary"][name] = {
                "description": desc,
                "sources": [source],
                "is_baseline": False,
            }
            vocab_added += 1
        else:
            # Добавляем source если ещё не записан
            if source not in data["vocabulary"][name]["sources"]:
                data["vocabulary"][name]["sources"].append(source)

    # Добавляем новые правила (дедупликация по формуле)
    existing_formulas = {r["formula"] for r in data["rules"]}
    for rule in new_rules:
        label = rule.get("label", "")
        formula = rule.get("formula", "")
        if not label or not formula:
            continue
        if formula not in existing_formulas:
            data["rules"].append({
                "label": label,
                "formula": formula,
                "sources": [source],
                "is_baseline": False,
            })
            existing_formulas.add(formula)
            rules_added += 1

    # Записываем в processed_files
    data["processed_files"][source] = {
        "status": "success",
        "timestamp": _now_iso(),
        "vocab_added": vocab_added,
        "rules_added": rules_added,
        "claims_found": claims_found,
    }

    data["metadata"]["total_processed"] += 1
    data["metadata"]["last_updated"] = _now_iso()

    _save_json(output_path, data)
    print(f"Merged: +{vocab_added} vocab, +{rules_added} rules from {source}")


# ---------------------------------------------------------------------------
# --record-error: зафиксировать ошибку обработки файла
# ---------------------------------------------------------------------------
def cmd_record_error(output_path: Path, source: str, error_msg: str) -> None:
    data = _load_json(output_path)

    data["processed_files"][source] = {
        "status": "error",
        "timestamp": _now_iso(),
        "error": error_msg,
    }

    data["metadata"]["total_errors"] += 1
    data["metadata"]["last_updated"] = _now_iso()

    _save_json(output_path, data)
    print(f"Recorded error for {source}: {error_msg}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Merge extraction results")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Initialize accumulated_results.json")
    p_init.add_argument("path", type=Path, help="Output JSON path")

    # merge
    p_merge = subparsers.add_parser("merge", help="Merge Claude output (stdin) into JSON")
    p_merge.add_argument("path", type=Path, help="Accumulated JSON path")
    p_merge.add_argument("--source", required=True, help="Relative path of processed file")

    # record-error
    p_err = subparsers.add_parser("record-error", help="Record processing error")
    p_err.add_argument("path", type=Path, help="Accumulated JSON path")
    p_err.add_argument("--source", required=True, help="Relative path of failed file")
    p_err.add_argument("--error-msg", required=True, help="Error message")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args.path)
    elif args.command == "merge":
        cmd_merge(args.path, args.source)
    elif args.command == "record-error":
        cmd_record_error(args.path, args.source, args.error_msg)


if __name__ == "__main__":
    main()
