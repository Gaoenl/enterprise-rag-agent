"""意图路由评估脚本。

用法：
  python scripts/evaluate_intent.py --mode rule    # 仅规则层
  python scripts/evaluate_intent.py --mode full    # 规则+向量+LLM（需服务可用）

指标：意图准确率、域命中率、漏检率、TOOL 识别率、CLARIFY 识别率。
"""

import argparse
import json
import sys
from pathlib import Path

# 保证 `python scripts/evaluate_intent.py` 也能找到 python-api 根目录下的 app 包。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.router.intent_router import IntentRouter
from app.rag.router.query_router import QueryRouter
from app.rag.schemas.routing_schema import L0Intent

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "datasets" / "intent_v1.json"


def load_cases(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def evaluate_rule(cases: list[dict]) -> dict:
    """仅规则层评估（不调用向量/LLM）。"""
    return _run(QueryRouter(), cases)


def evaluate_full(cases: list[dict]) -> dict:
    """完整路由评估（规则+向量+LLM）。"""
    return _run(IntentRouter(), cases)


def _run(router, cases: list[dict]) -> dict:
    total = intent_hit = domain_hit = knowledge_total = miss = 0
    tool_total = tool_hit = clarify_total = clarify_hit = 0
    inherit_cases = 0

    for case in cases:
        if case.get("inherit"):
            # 追问继承用例由多轮逻辑保证，这里单独计数。
            inherit_cases += 1
            continue

        total += 1
        decision = router.route(case["query"], [], None)
        expected = case["expected_intent"]

        if decision.intent.value == expected:
            intent_hit += 1
        if expected == "KNOWLEDGE":
            knowledge_total += 1
            if decision.need_rag is False:
                miss += 1  # 该检索没检索，漏检
            if decision.domain.value == case.get(
                "expected_domain", "GENERAL"
            ):
                domain_hit += 1
        if expected == "TOOL":
            tool_total += 1
            if decision.intent == L0Intent.TOOL:
                tool_hit += 1
        if expected == "CLARIFY":
            clarify_total += 1
            if decision.intent == L0Intent.CLARIFY:
                clarify_hit += 1

    return {
        "total": total,
        "intent_accuracy": round(intent_hit / total, 4) if total else 0,
        "domain_accuracy": (
            round(domain_hit / knowledge_total, 4)
            if knowledge_total
            else 0
        ),
        "miss_rate": round(miss / knowledge_total, 4) if knowledge_total else 0,
        "tool_accuracy": round(tool_hit / tool_total, 4) if tool_total else 0,
        "clarify_accuracy": (
            round(clarify_hit / clarify_total, 4)
            if clarify_total
            else 0
        ),
        "inherit_cases": inherit_cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="意图路由评估")
    parser.add_argument("--mode", choices=["rule", "full"], default="rule")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args()

    cases = load_cases(args.dataset)
    result = (
        evaluate_rule(cases)
        if args.mode == "rule"
        else evaluate_full(cases)
    )
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
