"""Turn a question into SQL. RuleBasedPlanner needs no API key; LLMPlanner is optional."""
from __future__ import annotations
import os, re, json
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Plan:
    sql: str
    reasoning: List[str] = field(default_factory=list)
    chart: str = "bar"          # bar | line | table
    x: Optional[str] = None
    y: Optional[str] = None
    planner: str = "rules"


AGG_WORDS = {"average": "AVG", "avg": "AVG", "mean": "AVG", "count": "COUNT", "how many": "COUNT",
             "number of": "COUNT", "max": "MAX", "highest": "MAX", "min": "MIN", "lowest": "MIN"}
TIME_HINTS = ("trend", "over time", "by month", "monthly", "per month", "drop", "fall", "fell", "decline", "change")


def _q(c: str) -> str:
    return '"' + c.replace('"', '""') + '"'


class RuleBasedPlanner:
    """Template matcher over the table schema. Deterministic, transparent, offline."""
    name = "rules"

    def plan(self, question: str, table: str, schema: Dict[str, str], samples: Dict[str, List[str]]) -> Plan:
        q = question.lower().strip()
        why: List[str] = []
        num = [c for c, t in schema.items() if any(k in t.upper() for k in ("INT", "DOUBLE", "DECIMAL", "FLOAT", "BIGINT", "REAL"))]
        cat = [c for c, t in schema.items() if "VARCHAR" in t.upper()]
        dates = [c for c, t in schema.items() if "DATE" in t.upper() or "TIMESTAMP" in t.upper()]

        # measure
        measure = next((c for c in num if c.lower() in q or c.lower().rstrip("s") in q), None)
        if measure is None:
            for alias, cands in (("sales", ("revenue", "sales", "amount")), ("revenue", ("revenue", "sales")),
                                 ("units", ("units", "quantity", "qty"))):
                if alias in q:
                    measure = next((c for c in num if c.lower() in cands), None)
                    if measure: break
        if measure is None and num:
            measure = num[0]
        why.append(f"Measure: '{measure}'" + (" (matched in question)" if measure and measure.lower() in q else " (default numeric column)"))

        agg = "SUM"
        for w, a in AGG_WORDS.items():
            if w in q:
                agg = a; break
        why.append(f"Aggregation: {agg}")

        # filters: any sample value mentioned in the question
        where = []
        for c in cat:
            for v in samples.get(c, []):
                if v and re.search(r"\b" + re.escape(v.lower()) + r"\b", q):
                    where.append(f"{_q(c)} = '{v.replace(chr(39), chr(39)*2)}'")
                    why.append(f"Filter: {c} = '{v}' (value found in question)")
        # group by
        group = None
        m = re.search(r"\b(?:by|per|each|across|which)\s+(\w+)", q)
        if m:
            word = m.group(1)
            group = next((c for c in cat + dates if c.lower() == word or c.lower().rstrip("s") == word.rstrip("s")), None)
        if group is None and any(h in q for h in TIME_HINTS) and dates:
            group = dates[0]
        if group is None:
            group = next((c for c in cat if c.lower() in q and not any(c in w for w in where)), None)

        mexpr = "COUNT(*)" if agg == "COUNT" else f"{agg}({_q(measure)})"
        alias = "count" if agg == "COUNT" else f"{agg.lower()}_{measure}"
        wsql = (" WHERE " + " AND ".join(where)) if where else ""
        top = re.search(r"\btop\s+(\d+)", q)
        if group:
            is_time = group in dates
            gexpr = f"date_trunc('month', {_q(group)})" if is_time else _q(group)
            order = "1" if is_time else f"{alias} DESC"
            sql = f"SELECT {gexpr} AS {_q(group)}, ROUND({mexpr}, 2) AS {alias} FROM {table}{wsql} GROUP BY 1 ORDER BY {order}"
            if top: sql += f" LIMIT {int(top.group(1))}"
            why.append(f"Group by: {group}" + (" (monthly, because the question is about change over time)" if is_time else ""))
            return Plan(sql, why, "line" if is_time else "bar", group, alias)
        sql = f"SELECT ROUND({mexpr}, 2) AS {alias} FROM {table}{wsql}"
        why.append("No grouping detected: returning a single number")
        return Plan(sql, why, "table", None, alias)


class LLMPlanner:
    """Uses any OpenAI-compatible endpoint (OpenAI, xAI, local Ollama...). Falls back to rules on error."""
    name = "llm"

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.model = model or os.getenv("AYD_MODEL", "gpt-4o-mini")
        self.base_url = base_url or os.getenv("AYD_BASE_URL")
        self.api_key = api_key or os.getenv("AYD_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.fallback = RuleBasedPlanner()

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def plan(self, question, table, schema, samples) -> Plan:
        if not self.available:
            p = self.fallback.plan(question, table, schema, samples)
            p.reasoning.insert(0, "No LLM key set: used rule-based planner")
            return p
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            prompt = (f"Table {table} columns: {json.dumps(schema)}. Sample values: {json.dumps(samples)[:1500]}.\n"
                      f"Write one DuckDB SELECT answering: {question}\nReply JSON: "
                      '{"sql":"...","reasoning":["..."],"chart":"bar|line|table","x":"col or null","y":"col"}')
            r = client.chat.completions.create(model=self.model, messages=[{"role": "user", "content": prompt}],
                                               response_format={"type": "json_object"}, temperature=0)
            d = json.loads(r.choices[0].message.content)
            return Plan(d["sql"], d.get("reasoning", []), d.get("chart", "table"), d.get("x"), d.get("y"), "llm")
        except Exception as e:  # noqa: BLE001
            p = self.fallback.plan(question, table, schema, samples)
            p.reasoning.insert(0, f"LLM failed ({type(e).__name__}): used rule-based planner")
            return p
