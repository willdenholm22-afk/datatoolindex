"""
Content pipeline for GEO affiliate hub.

Reads tool data from D1 (or tools_seed.json locally), generates MDX pages for:
  - Individual tool pages
  - Pairwise comparisons
  - Use-case pages
Validates each output against quality rules, writes to src/content/, commits to git.

Run locally: python content_pipeline.py --generate tools
Scheduled: GitHub Actions cron runs --refresh weekly
"""
import argparse
import itertools
import json
import os
import re
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

from anthropic import Anthropic

ANTHROPIC = Anthropic()
MODEL = "claude-opus-4-7"
CONTENT_ROOT = Path("src/content")
PROMPT_FILE = Path("content_generation_prompt.md")
SEED_FILE = Path("tools_seed.json")
REFRESH_STALE_DAYS = 30

BANNED_PHRASES = [
    "revolutionary", "game-changing", "cutting-edge",
    "in today's fast-paced", "leverage", "synergy",
    "unlock the power", "transform your",
]


# ---------- Data loading ----------
def load_tools():
    with open(SEED_FILE) as f:
        return json.load(f)["tools"]


def load_prompts():
    with open(PROMPT_FILE) as f:
        return f.read()


# ---------- Generation ----------
def generate_page(page_type: str, context: dict, prompts_text: str) -> str:
    system = _extract_section(prompts_text, "System prompt")
    user_template = _extract_section(prompts_text, f"{page_type} page prompt")
    user = _fill(user_template, context)

    for attempt in range(3):
        response = ANTHROPIC.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        mdx = response.content[0].text
        errors = validate_mdx(mdx, context)
        if not errors:
            return mdx
        # retry with feedback
        user = user + f"\n\nPREVIOUS ATTEMPT FAILED VALIDATION:\n{errors}\nFix and regenerate."
    raise RuntimeError(f"Failed after 3 attempts. Errors: {errors}")


def validate_mdx(mdx: str, context: dict) -> list[str]:
    errors = []
    if "---" not in mdx[:10]:
        errors.append("Missing frontmatter")
    if '<script type="application/ld+json">' not in mdx:
        errors.append("Missing JSON-LD script block")
    else:
        # validate JSON-LD parses
        for match in re.finditer(
            r'<script type="application/ld\+json">(.*?)</script>', mdx, re.DOTALL
        ):
            try:
                json.loads(match.group(1))
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON-LD: {e}")
    if "|" not in mdx:  # crude but catches table absence
        errors.append("Missing comparison/pricing table")
    if not re.search(r"(verified|as of)\s+\w+\s+2026", mdx, re.IGNORECASE):
        errors.append("Missing dated fact assertion")

    word_count = len(mdx.split())
    if word_count < 700:
        errors.append(f"Word count {word_count} below 700")
    if word_count > 3000:
        errors.append(f"Word count {word_count} exceeds 3000")

    for phrase in BANNED_PHRASES:
        if phrase.lower() in mdx.lower():
            errors.append(f"Banned phrase: '{phrase}'")

    # affiliate URL check for tool pages
    if "affiliate_url" in context and context["affiliate_url"]:
        if context["affiliate_url"] not in mdx:
            errors.append("Affiliate URL missing from output")

    return errors


# ---------- Page builders ----------
def build_tool_pages(tools, prompts_text):
    (CONTENT_ROOT / "tools").mkdir(parents=True, exist_ok=True)
    for tool in tools:
        out_path = CONTENT_ROOT / "tools" / f"{tool['slug']}.mdx"
        if _is_fresh(out_path):
            continue
        ctx = {
            "tool_json": json.dumps(tool),
            "research_notes": tool.get("research_notes", ""),
            "affiliate_url": tool.get("affiliate_url", ""),
            "date": date.today().isoformat(),
            "author": "Will",
        }
        mdx = generate_page("Tool", ctx, prompts_text)
        out_path.write_text(mdx)
        print(f"✓ {out_path}")


def build_comparison_pages(tools, prompts_text):
    (CONTENT_ROOT / "compare").mkdir(parents=True, exist_ok=True)
    # only pairs within same category (more relevant + higher quality)
    by_category = {}
    for t in tools:
        by_category.setdefault(t["category"], []).append(t)

    for cat_tools in by_category.values():
        for a, b in itertools.combinations(cat_tools, 2):
            slug = f"{a['slug']}-vs-{b['slug']}"
            out_path = CONTENT_ROOT / "compare" / f"{slug}.mdx"
            if _is_fresh(out_path):
                continue
            ctx = {
                "tool_a_json": json.dumps(a),
                "tool_b_json": json.dumps(b),
                "research_notes": f"A:{a.get('research_notes','')}\nB:{b.get('research_notes','')}",
                "affiliate_a": a.get("affiliate_url", ""),
                "affiliate_b": b.get("affiliate_url", ""),
                "date": date.today().isoformat(),
                "author": "Will",
            }
            mdx = generate_page("Comparison", ctx, prompts_text)
            out_path.write_text(mdx)
            print(f"✓ {out_path}")


def build_use_case_pages(tools, use_cases, prompts_text):
    (CONTENT_ROOT / "use-cases").mkdir(parents=True, exist_ok=True)
    tools_by_slug = {t["slug"]: t for t in tools}
    for uc in use_cases:
        out_path = CONTENT_ROOT / "use-cases" / f"{uc['slug']}.mdx"
        if _is_fresh(out_path):
            continue
        candidates = [tools_by_slug[s] for s in uc["candidate_tool_slugs"] if s in tools_by_slug]
        ctx = {
            "use_case_question": uc["question"],
            "tools_json_array": json.dumps(candidates),
            "research_notes": uc.get("research_notes", ""),
            "affiliate_map": json.dumps({t["slug"]: t.get("affiliate_url", "") for t in candidates}),
            "date": date.today().isoformat(),
            "author": "Will",
        }
        mdx = generate_page("Use-case", ctx, prompts_text)
        out_path.write_text(mdx)
        print(f"✓ {out_path}")


# ---------- Deploy ----------
def commit_and_push():
    subprocess.run(["git", "add", "src/content"], check=True)
    result = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if result.returncode == 0:
        print("No changes to commit.")
        return
    subprocess.run(
        ["git", "commit", "-m", f"content: auto-refresh {date.today()}"], check=True
    )
    subprocess.run(["git", "push"], check=True)
    print("Pushed.")


# ---------- Utilities ----------
def _fill(template: str, ctx: dict) -> str:
    for k, v in ctx.items():
        template = template.replace("{" + k + "}", str(v))
    return template


def _extract_section(text: str, header: str) -> str:
    # crude section extractor; expects ### or ## {header} in prompts file
    pattern = rf"###?\s+{re.escape(header)}\s*\n+(.*?)(?=\n###? |\Z)"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _is_fresh(path: Path, stale_days: int = REFRESH_STALE_DAYS) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return (datetime.now() - mtime) < timedelta(days=stale_days)


# ---------- Entry ----------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--generate",
        choices=["tools", "comparisons", "use-cases", "all"],
        default="all",
    )
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()

    seed = json.load(open(SEED_FILE))
    tools = seed["tools"]
    use_cases = seed.get("use_cases", [])
    prompts_text = load_prompts()

    if args.generate in ("tools", "all"):
        build_tool_pages(tools, prompts_text)
    if args.generate in ("comparisons", "all"):
        build_comparison_pages(tools, prompts_text)
    if args.generate in ("use-cases", "all"):
        build_use_case_pages(tools, use_cases, prompts_text)

    if args.push:
        commit_and_push()


if __name__ == "__main__":
    main()
