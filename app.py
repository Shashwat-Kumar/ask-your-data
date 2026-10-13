"""Streamlit UI:  streamlit run app.py"""
import tempfile
import streamlit as st
from ask_your_data import Ask, RuleBasedPlanner, LLMPlanner

st.set_page_config(page_title="Ask Your Data", layout="wide")
st.title("Ask Your Data")
st.caption("Plain English in, SQL and a chart out. Runs locally on DuckDB. Sample data is synthetic.")
up = st.file_uploader("CSV, Parquet or SQLite", type=["csv", "parquet", "db", "sqlite"])
path = "data/sample_sales.csv"
if up:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix="." + up.name.split(".")[-1]); tmp.write(up.read()); path = tmp.name
use_llm = st.sidebar.toggle("Use LLM planner (needs AYD_API_KEY)", value=False)
ask = Ask(path, planner=LLMPlanner() if use_llm else RuleBasedPlanner())
st.sidebar.write("**Schema**")
st.sidebar.json(ask.schema)
q = st.text_input("Question", "Why did revenue drop in Pune? Show revenue by month")
if q:
    ans = ask.ask(q)
    c1, c2 = st.columns([3, 2])
    c1.pyplot(ans.chart())
    c2.subheader("Reasoning")
    for r in ans.plan.reasoning:
        c2.markdown(f"- {r}")
    c2.subheader("SQL"); c2.code(ans.plan.sql, language="sql", wrap_lines=True)
    st.dataframe(ans.df, width="stretch")
