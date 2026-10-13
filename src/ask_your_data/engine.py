from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

from .planner import Plan, RuleBasedPlanner

FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|attach|copy|pragma|install|load|export)\b", re.I)


@dataclass
class Answer:
    question: str
    plan: Plan
    df: pd.DataFrame

    def chart(self, path: Optional[str] = None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(8, 4.2))
        p, df = self.plan, self.df
        if p.chart in ("bar", "line") and p.x in df.columns and p.y in df.columns:
            x = df[p.x].astype(str).str[:10] if p.chart == "line" else df[p.x].astype(str)
            (ax.plot(x, df[p.y], marker="o", color="#6c5ce7") if p.chart == "line"
             else ax.bar(x, df[p.y], color="#6c5ce7"))
            ax.set_xlabel(p.x); ax.set_ylabel(p.y)
            plt.setp(ax.get_xticklabels(), rotation=35, ha="right")
        else:
            ax.axis("off")
            ax.table(cellText=df.head(15).values, colLabels=list(df.columns), loc="center")
        ax.set_title(self.question, fontsize=11)
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        if path:
            fig.savefig(path, dpi=130)
        return fig


class Ask:
    """Load a CSV / Parquet / SQLite table into DuckDB and answer questions about it (read-only SQL)."""

    def __init__(self, source: str, table: Optional[str] = None, planner=None):
        self.con = duckdb.connect()
        src = Path(source)
        if src.suffix in (".db", ".sqlite", ".sqlite3"):
            import sqlite3
            with sqlite3.connect(str(src)) as sc:
                names = [r[0] for r in sc.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                t = table or names[0]
                self._df = pd.read_sql_query(f'SELECT * FROM "{t}"', sc)
            self.con.register("data", self._df)
        else:
            reader = "read_parquet" if src.suffix == ".parquet" else "read_csv_auto"
            self.con.execute(f"CREATE VIEW data AS SELECT * FROM {reader}('{src}')")
        self.table = "data"
        self.planner = planner or RuleBasedPlanner()
        self.schema = {r[0]: r[1] for r in self.con.execute("DESCRIBE data").fetchall()}
        self.samples = {}
        for c, t in self.schema.items():
            if "VARCHAR" in t:
                self.samples[c] = [r[0] for r in self.con.execute(
                    f'SELECT DISTINCT "{c}" FROM data WHERE "{c}" IS NOT NULL LIMIT 50').fetchall()]

    def sql(self, query: str) -> pd.DataFrame:
        if not query.lstrip().lower().startswith(("select", "with")) or FORBIDDEN.search(query):
            raise ValueError("Only read-only SELECT queries are allowed")
        return self.con.execute(query).df()

    def ask(self, question: str) -> Answer:
        plan = self.planner.plan(question, self.table, self.schema, self.samples)
        return Answer(question, plan, self.sql(plan.sql))
