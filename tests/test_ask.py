import sqlite3, pandas as pd, pytest
from ask_your_data import Ask, LLMPlanner

CSV = "data/sample_sales.csv"

@pytest.fixture(scope="module")
def ask(): return Ask(CSV)

def test_schema(ask):
    assert {"city", "revenue", "order_month"} <= set(ask.schema)

def test_by_city(ask):
    a = ask.ask("total revenue by city")
    assert list(a.df.columns) == ["city", "sum_revenue"] and len(a.df) == 6

def test_filter_and_time(ask):
    a = ask.ask("Why did revenue drop in Pune?")
    assert "Pune" in a.plan.sql and a.plan.chart == "line" and len(a.df) == 12
    assert a.df["sum_revenue"].iloc[-1] < a.df["sum_revenue"].iloc[0]

def test_single_number(ask):
    a = ask.ask("average units")
    assert a.df.shape == (1, 1) and "AVG" in a.plan.sql

def test_top_n(ask):
    assert len(ask.ask("top 2 product by revenue").df) == 2

def test_count(ask):
    assert ask.ask("how many rows").df.iloc[0, 0] == 576

def test_readonly(ask):
    with pytest.raises(ValueError):
        ask.sql("DROP VIEW data")

def test_chart(ask, tmp_path):
    p = tmp_path / "c.png"; ask.ask("revenue by channel").chart(str(p)); assert p.stat().st_size > 1000

def test_llm_falls_back_without_key(monkeypatch):
    for k in ("AYD_API_KEY", "OPENAI_API_KEY"): monkeypatch.delenv(k, raising=False)
    a = Ask(CSV, planner=LLMPlanner()).ask("revenue by city")
    assert "No LLM key" in a.plan.reasoning[0]

def test_sqlite(tmp_path):
    db = tmp_path / "s.db"
    with sqlite3.connect(db) as c: pd.read_csv(CSV).to_sql("sales", c)
    assert len(Ask(str(db)).ask("revenue by product").df) == 4
