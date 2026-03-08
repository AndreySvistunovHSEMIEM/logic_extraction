#!/usr/bin/env python3
"""Async pipeline извлечения словаря и правил из IT-резюме через Claude CLI.

Использование:
    python3 extract_pipeline.py          # обработать все оставшиеся
    python3 extract_pipeline.py -n 50    # обработать максимум 50 файлов
    python3 extract_pipeline.py -n 50 -c 5  # 5 параллельных сессий (по умолчанию 10)
"""

import argparse
import asyncio
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
RESUME_ROOT = PROJECT_ROOT / "HRom_resume_fabricated"

RESULTS_JSON = SCRIPT_DIR / "accumulated_results.json"
PROMPT_TEMPLATE = SCRIPT_DIR / "prompt_template.txt"
LOG_FILE = SCRIPT_DIR / "pipeline.log"

MAX_RETRIES = 2
RATE_LIMIT_BACKOFF = 60  # секунд ожидания при лимите
RATE_LIMIT_PATTERNS = [
    "rate limit", "too many requests", "429", "quota exceeded",
    "overloaded", "capacity", "try again later", "resource_exhausted",
]

RESUME_DIRS = [
    "CV_mostly_English_done/cv_mostly_english",
    "Flood_resume_CV_done",
    "OM_Stepan_Flood_Resume_done/flood_resume_cv",
    "Resume_mostly_Russian/resume_almost_russian",
]

ALLOWED_EXT = {"pdf"}


# ---------------------------------------------------------------------------
# Rate-limit detection & global pause
# ---------------------------------------------------------------------------
def _is_rate_limit(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in RATE_LIMIT_PATTERNS)


class RateLimitGuard:
    """Глобальная пауза: когда один воркер ловит лимит, все остальные ждут."""

    def __init__(self):
        self._event = asyncio.Event()
        self._event.set()  # изначально открыто
        self._lock = asyncio.Lock()
        self._resume_at: float = 0

    async def pause(self, seconds: int) -> None:
        async with self._lock:
            import time
            target = time.monotonic() + seconds
            if target <= self._resume_at:
                return  # уже ждём дольше
            self._resume_at = target
            self._event.clear()
            log.warning("Rate limit hit — pausing ALL workers for %d sec", seconds)

        await asyncio.sleep(seconds)
        self._event.set()
        log.info("Rate limit pause ended, resuming workers")

    async def wait(self) -> None:
        """Каждый воркер вызывает перед запросом."""
        await self._event.wait()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log = logging.getLogger("pipeline")


def setup_logging() -> None:
    fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(fh)
    log.addHandler(sh)
    log.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_data() -> dict:
    with open(RESULTS_JSON, encoding="utf-8") as f:
        return json.load(f)


def save_data(data: dict) -> None:
    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------
def init_results() -> dict:
    """Создать baseline из domain/rules.py."""
    rules_py = SCRIPT_DIR.parent / "domain" / "rules.py"
    ns: dict = {}
    exec(rules_py.read_text(encoding="utf-8"), ns)

    vocabulary = {}
    for name, desc in ns["DOMAIN_VOCABULARY"].items():
        vocabulary[name] = {"description": desc, "sources": [], "is_baseline": True}

    rules = []
    for label, formula in ns["DOMAIN_RULES"]:
        rules.append({"label": label, "formula": formula, "sources": [], "is_baseline": True})

    data = {
        "metadata": {"last_updated": _now_iso(), "total_processed": 0, "total_errors": 0},
        "vocabulary": vocabulary,
        "rules": rules,
        "processed_files": {},
    }
    save_data(data)
    log.info("Initialized: %d vocab + %d rules", len(vocabulary), len(rules))
    return data


# ---------------------------------------------------------------------------
# Collect files
# ---------------------------------------------------------------------------
def collect_files(data: dict, max_files: int) -> list[tuple[Path, str]]:
    """Собрать список (abs_path, rel_path) необработанных файлов."""
    processed = data.get("processed_files", {})
    files: list[tuple[Path, str]] = []

    for dir_rel in RESUME_DIRS:
        dir_abs = RESUME_ROOT / dir_rel
        if not dir_abs.is_dir():
            log.warning("Directory not found: %s", dir_abs)
            continue

        for f in sorted(dir_abs.iterdir()):
            if not f.is_file():
                continue
            ext = f.suffix.lstrip(".").lower()
            if ext not in ALLOWED_EXT:
                continue
            rel = str(f.relative_to(RESUME_ROOT))
            if processed.get(rel, {}).get("status") == "success":
                continue
            files.append((f, rel))
            if 0 < max_files <= len(files):
                return files

    return files


# ---------------------------------------------------------------------------
# Build prompt
# ---------------------------------------------------------------------------
def build_prompt(resume_path: Path) -> str:
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    return template.replace("$RESUME_PATH", str(resume_path))


# ---------------------------------------------------------------------------
# Parse Claude response
# ---------------------------------------------------------------------------
def parse_claude_output(raw: str) -> dict | None:
    """Извлечь JSON с new_vocabulary/new_rules из ответа Claude CLI."""
    text = raw.strip()

    # Claude CLI --output-format json wraps in {"result": "..."}
    try:
        envelope = json.loads(text)
        text = envelope.get("result", text)
    except json.JSONDecodeError:
        pass

    # Strip markdown fences
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    # Try direct parse
    try:
        parsed = json.loads(text)
        if "new_vocabulary" in parsed and "new_rules" in parsed:
            return parsed
    except json.JSONDecodeError:
        pass

    # Try regex extraction
    m = re.search(r'\{[\s\S]*"new_vocabulary"[\s\S]*\}', text)
    if m:
        try:
            parsed = json.loads(m.group())
            if "new_vocabulary" in parsed and "new_rules" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    return None


# ---------------------------------------------------------------------------
# Merge result into data (under lock)
# ---------------------------------------------------------------------------
def merge_result(data: dict, source: str, result: dict) -> tuple[int, int]:
    """Merge Claude result into data. Returns (vocab_added, rules_added)."""
    new_vocab = result.get("new_vocabulary", {})
    new_rules = result.get("new_rules", [])
    claims_found = result.get("claims_found", 0)

    vocab_added = 0
    rules_added = 0

    for name, desc in new_vocab.items():
        if name not in data["vocabulary"]:
            data["vocabulary"][name] = {
                "description": desc,
                "sources": [source],
                "is_baseline": False,
            }
            vocab_added += 1
        else:
            if source not in data["vocabulary"][name]["sources"]:
                data["vocabulary"][name]["sources"].append(source)

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

    data["processed_files"][source] = {
        "status": "success",
        "timestamp": _now_iso(),
        "vocab_added": vocab_added,
        "rules_added": rules_added,
        "claims_found": claims_found,
    }
    data["metadata"]["total_processed"] += 1
    data["metadata"]["last_updated"] = _now_iso()

    return vocab_added, rules_added


def record_error(data: dict, source: str, error_msg: str) -> None:
    data["processed_files"][source] = {
        "status": "error",
        "timestamp": _now_iso(),
        "error": error_msg,
    }
    data["metadata"]["total_errors"] += 1
    data["metadata"]["last_updated"] = _now_iso()


# ---------------------------------------------------------------------------
# Process one file
# ---------------------------------------------------------------------------
async def process_file(
    abs_path: Path,
    rel_path: str,
    data: dict,
    lock: asyncio.Lock,
    sem: asyncio.Semaphore,
    counter: dict,
    guard: RateLimitGuard,
) -> None:
    async with sem:
        counter["started"] += 1
        idx = counter["started"]
        total_so_far = counter["already"] + idx
        log.info("[%d total, #%d this run] Processing: %s", total_so_far, idx, rel_path)

        prompt = build_prompt(abs_path)

        last_error = ""
        attempt = 0
        while attempt < MAX_RETRIES + 1:
            attempt += 1
            log.info("  Attempt %d/%d for %s", attempt, MAX_RETRIES + 1, rel_path)

            # Wait if global rate-limit pause is active
            await guard.wait()

            try:
                proc = await asyncio.create_subprocess_exec(
                    "claude", "-p", prompt,
                    "--allowedTools", "Read",
                    "--output-format", "json",
                    "--model", "sonnet",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()

                if proc.returncode != 0:
                    last_error = stderr.decode(errors="replace").strip()[:500]
                    stdout_text = stdout.decode(errors="replace").strip()[:500]
                    combined = f"{last_error} {stdout_text}"

                    if _is_rate_limit(combined):
                        log.warning("  Rate limit for %s: %s", rel_path, last_error[:200])
                        await guard.pause(RATE_LIMIT_BACKOFF)
                        attempt -= 1  # не считаем лимит как попытку
                        continue

                    log.warning("  claude CLI failed (rc=%d): %s", proc.returncode, last_error[:200])
                    if attempt <= MAX_RETRIES:
                        await asyncio.sleep(5)
                    continue

                raw_output = stdout.decode(errors="replace")

                # Rate limit может прийти и в stdout (в JSON-обёртке)
                if _is_rate_limit(raw_output):
                    log.warning("  Rate limit in stdout for %s", rel_path)
                    await guard.pause(RATE_LIMIT_BACKOFF)
                    attempt -= 1
                    continue

                parsed = parse_claude_output(raw_output)
                if parsed is None:
                    last_error = "Could not parse JSON from Claude response"
                    log.warning("  %s for %s", last_error, rel_path)
                    log.warning("  Raw response (first 500 chars): %s", raw_output[:500])
                    if attempt <= MAX_RETRIES:
                        await asyncio.sleep(5)
                    continue

                # Success — merge under lock
                async with lock:
                    va, ra = merge_result(data, rel_path, parsed)
                    save_data(data)

                counter["done"] += 1
                log.info(
                    "  OK: +%d vocab, +%d rules from %s [%d/%d done]",
                    va, ra, rel_path, counter["done"], counter["total"],
                )
                return

            except Exception as e:
                last_error = str(e)[:200]
                log.warning("  Exception: %s", last_error)
                if attempt <= MAX_RETRIES:
                    await asyncio.sleep(5)

        # All retries failed
        async with lock:
            record_error(data, rel_path, f"All {MAX_RETRIES + 1} attempts failed: {last_error}")
            save_data(data)

        counter["errors"] += 1
        log.error("  FAILED: %s", rel_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def run(max_files: int, concurrency: int) -> None:
    setup_logging()

    # Init if needed
    if not RESULTS_JSON.exists():
        data = init_results()
    else:
        data = load_data()

    already = len(data.get("processed_files", {}))
    files = collect_files(data, max_files)

    if not files:
        log.info("No files to process. Already processed: %d", already)
        return

    log.info("=== Pipeline started ===")
    log.info("Already processed: %d files", already)
    log.info("To process: %d files, concurrency: %d", len(files), concurrency)

    lock = asyncio.Lock()
    sem = asyncio.Semaphore(concurrency)
    guard = RateLimitGuard()
    counter = {
        "already": already,
        "started": 0,
        "done": 0,
        "errors": 0,
        "total": len(files),
    }

    tasks = [
        asyncio.create_task(process_file(abs_p, rel_p, data, lock, sem, counter, guard))
        for abs_p, rel_p in files
    ]

    await asyncio.gather(*tasks)

    log.info("=== Pipeline finished ===")
    log.info(
        "This run: %d done, %d errors. Overall: %d processed.",
        counter["done"],
        counter["errors"],
        already + counter["done"] + counter["errors"],
    )

    # Final stats
    data = load_data()
    log.info(
        "Totals: %d vocab, %d rules, %d processed, %d errors",
        len(data["vocabulary"]),
        len(data["rules"]),
        len(data["processed_files"]),
        data["metadata"]["total_errors"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Async pipeline извлечения словаря и правил из IT-резюме"
    )
    parser.add_argument(
        "-n", "--max-files", type=int, default=0,
        help="Макс. кол-во файлов для обработки (0 = все)",
    )
    parser.add_argument(
        "-c", "--concurrency", type=int, default=10,
        help="Кол-во параллельных сессий Claude (по умолчанию 10)",
    )
    args = parser.parse_args()
    asyncio.run(run(args.max_files, args.concurrency))


if __name__ == "__main__":
    main()
