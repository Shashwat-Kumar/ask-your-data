import argparse, sys
from .engine import Ask
from .planner import LLMPlanner, RuleBasedPlanner

def main(argv=None):
    ap = argparse.ArgumentParser(prog="ask-your-data")
    ap.add_argument("source", help="CSV, Parquet or SQLite file")
    ap.add_argument("question")
    ap.add_argument("--llm", action="store_true", help="Use LLM planner (needs AYD_API_KEY)")
    ap.add_argument("--chart", help="Save chart PNG here")
    a = ap.parse_args(argv)
    ask = Ask(a.source, planner=LLMPlanner() if a.llm else RuleBasedPlanner())
    ans = ask.ask(a.question)
    print("Reasoning:"); [print("  -", r) for r in ans.plan.reasoning]
    print("\nSQL:\n ", ans.plan.sql, "\n"); print(ans.df.to_string(index=False))
    if a.chart: ans.chart(a.chart); print(f"\nChart saved to {a.chart}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
