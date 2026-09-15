import streamlit as st
import pandas as pd

st.set_page_config(page_title="Half-PPR Start/Sit", layout="wide")
st.title("Half-PPR Start / Sit")
st.caption("Sleeper username in the sidebar. Cloud version.")

st.sidebar.header("Settings")
week = st.sidebar.number_input("NFL week", min_value=1, max_value=18, value=1)
positions = st.sidebar.multiselect(
    "Positions", ["QB", "RB", "WR", "TE"], default=["QB", "RB", "WR", "TE"]
)
username = st.sidebar.text_input("Sleeper username")

st.info(
    "Site is live. Full Sleeper + DVP engine is on your Chromebook. "
    "This Cloud page is the public shell until those modules are uploaded."
)

df = pd.DataFrame(
    [
        {
            "player": "Example RB",
            "pos": "RB",
            "opp": "vs KC",
            "base": 12.4,
            "matchup": "Avg",
            "proj": 12.4,
            "call": "Lean Start",
        },
        {
            "player": "Example WR",
            "pos": "WR",
            "opp": "@ DEN",
            "base": 9.1,
            "matchup": "Easy (28/32)",
            "proj": 10.2,
            "call": "Strong Start",
        },
    ]
)
if positions:
    df = df[df["pos"].isin(positions)]

st.subheader(f"Week {week} board (Half-PPR)")
st.dataframe(df, use_container_width=True, hide_index=True)

if username:
    st.success(f"Sleeper user entered: {username}")
    st.write("Roster sync will return after data/sleeper.py is on GitHub.")
