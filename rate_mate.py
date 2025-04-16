"""
Rate Mate v0.1
Streamlit dashboard for LSCO logistics: consumption vs capacity.
"""

import os
import streamlit as st
import pandas as pd
from datetime import datetime

# ──────────────────────────────────────────────────────────────────────────────
# Constants & Version
VERSION = "0.1"
RATE_SUFFIX = "_rate"
CAP_SUFFIX  = "_cap"
CONSUMPTION_CSV = "consumption.csv"
CAPACITY_CSV    = "capacities.csv"
# ──────────────────────────────────────────────────────────────────────────────

def load_consumption(path):
    """Load consumption CSV, validate unit_type/action and at least one *_rate."""
    if not os.path.exists(path):
        st.error(f"Consumption CSV not found: {path}")
        st.stop()
    df = pd.read_csv(path)
    if 'unit_type' not in df.columns or 'action' not in df.columns:
        st.error(f"{path} must contain 'unit_type' and 'action' columns.")
        st.stop()
    if not any(col.endswith(RATE_SUFFIX) for col in df.columns):
        st.error(f"{path} must contain at least one '{RATE_SUFFIX}' column.")
        st.stop()
    return df

def load_capacity(path):
    """Load capacity CSV, validate unit_type and at least one *_cap."""
    if not os.path.exists(path):
        st.error(f"Capacity CSV not found: {path}")
        st.stop()
    df = pd.read_csv(path)
    if 'unit_type' not in df.columns:
        st.error(f"{path} must contain 'unit_type' column.")
        st.stop()
    if not any(col.endswith(CAP_SUFFIX) for col in df.columns):
        st.error(f"{path} must contain at least one '{CAP_SUFFIX}' column.")
        st.stop()
    return df

@st.cache_data
def load_data():
    """Load and return (consumption_df, capacity_df)."""
    cons = load_consumption(CONSUMPTION_CSV)
    cap  = load_capacity(CAPACITY_CSV)
    return cons, cap

def compute_totals(cons_df, cap_df, action, unit_counts, sel_rates, sel_caps):
    """Compute detailed and total consumption/capacity for the selected action."""
    # Consumption
    req = cons_df[cons_df["action"] == action].copy()
    req["count"] = req["unit_type"].map(unit_counts).fillna(0).astype(int)
    req_detail = req[["unit_type","action","count"] + sel_rates].copy()
    req_detail.loc[:, sel_rates] = req_detail[sel_rates].multiply(req_detail["count"], axis=0)
    total_req = req_detail[sel_rates].sum()

    # Capacity
    cap = cap_df.copy()
    cap["count"] = cap["unit_type"].map(unit_counts).fillna(0).astype(int)
    cap_detail = cap[["unit_type","count"] + sel_caps].copy()
    cap_detail.loc[:, sel_caps] = cap_detail[sel_caps].multiply(cap_detail["count"], axis=0)
    total_cap = cap_detail[sel_caps].sum()

    return req_detail, cap_detail, total_req, total_cap

def group_prefix(col):
    """Determine grouping prefix for a subtype column."""
    if col.startswith("CL_"):
        parts = col.split("_")
        return f"{parts[0]}_{parts[1]}"    # e.g. CL_III, CL_V, CL_IX
    if col.startswith("Recovery_"):
        return "Recovery"
    return col.split("_")[0]               # e.g. Javelin, 105mm

def build_group_summary(total_req, total_cap, sel_rates, sel_caps):
    """Build DataFrame summarizing by prefix group."""
    groups = sorted({ group_prefix(c) for c in sel_rates + sel_caps })
    rows = []
    for grp in groups:
        grp_rates = [c for c in sel_rates if group_prefix(c)==grp]
        grp_caps  = [c for c in sel_caps  if group_prefix(c)==grp]
        req_sum = total_req[grp_rates].sum() if grp_rates else 0
        cap_sum = total_cap[grp_caps].sum()   if grp_caps  else 0
        surplus = cap_sum - req_sum

        # Bulk vs Wheeled for CL_III
        bulk_keys  = [c for c in grp_caps if "_bulk_cap"    in c]
        wheel_keys = [c for c in grp_caps if "_wheeled_cap" in c]
        bulk_sum   = total_cap[bulk_keys].sum()   if bulk_keys  else None
        wheel_sum  = total_cap[wheel_keys].sum()  if wheel_keys else None
        bulk_surp  = (bulk_sum - req_sum) if bulk_sum  is not None else None
        wheel_surp = (wheel_sum - req_sum) if wheel_sum is not None else None

        # Deficit subtypes if group is overall deficit
        deficit = []
        if surplus < 0:
            for rate in grp_rates:
                base = rate.replace(RATE_SUFFIX,"")
                cap_matches = [c for c in sel_caps if c.startswith(base)]
                if total_req[rate] > sum(total_cap[c] for c in cap_matches):
                    deficit.append(base)

        row = {
            "Group": grp,
            "Requirement": req_sum,
            "Capacity":    cap_sum,
            "Surplus/(Deficit)": surplus,
            "Deficit Subtypes": ", ".join(deficit) if deficit else "-"
        }
        if bulk_sum is not None:
            row["Bulk Cap"]    = bulk_sum
            row["Bulk Surplus"] = bulk_surp
        if wheel_sum is not None:
            row["Wheeled Cap"]     = wheel_sum
            row["Wheeled Surplus"] = wheel_surp

        rows.append(row)

    return pd.DataFrame(rows).set_index("Group")

def fmt_parenthesis(x):
    """Format number with commas; negative in parentheses."""
    if pd.isna(x):
        return "-"
    i = int(x)
    return f"({abs(i):,})" if i < 0 else f"{i:,}"

# ──────────────────────────────────────────────────────────────────────────────
# Load data
cons_df, cap_df = load_data()

st.set_page_config(page_title=f"Rate Mate v{VERSION}", layout="wide")

# Version info
ts = datetime.fromtimestamp(os.path.getmtime(CONSUMPTION_CSV))
st.markdown(f"**Rate Mate v{VERSION} | Data loaded: {ts:%Y-%m-%d %H:%M}**")

# Sidebar: Data & Overrides
st.sidebar.header("Data & Overrides")
def editable(df, key):
    if hasattr(st, "data_editor"):
        return st.data_editor(df, num_rows="dynamic", key=key)
    if hasattr(st, "experimental_data_editor"):
        return st.experimental_data_editor(df, num_rows="dynamic", key=key)
    st.sidebar.warning("Upgrade Streamlit ≥1.18 to edit tables.")
    return df

with st.sidebar.expander("Edit CSV Tables"):
    cons_df = editable(cons_df, "cons_override")
    cap_df  = editable(cap_df,  "cap_override")

# Sidebar: Filters & Counts
st.sidebar.header("Filters & Counts")
action = st.sidebar.selectbox("Operational Action", cons_df["action"].unique())

unit_counts = {
    u: st.sidebar.number_input(f"{u} count", min_value=0, value=1, step=1)
    for u in cons_df["unit_type"].unique()
}

rate_cols = [c for c in cons_df.columns if c.endswith(RATE_SUFFIX)]
cap_cols  = [c for c in cap_df.columns  if c.endswith(CAP_SUFFIX)]

with st.sidebar.expander("Select Subtypes to Include"):
    selected_rates = st.multiselect("Consumption subtypes", rate_cols, default=rate_cols)
    selected_caps  = st.multiselect("Capacity subtypes",    cap_cols,  default=cap_cols)

if not selected_rates or not selected_caps:
    st.error("Select at least one consumption and one capacity subtype.")
    st.stop()

# Compute details & totals
req_detail, cap_detail, total_req, total_cap = compute_totals(
    cons_df, cap_df, action, unit_counts, selected_rates, selected_caps
)

# Build grouped summary
group_df = build_group_summary(total_req, total_cap, selected_rates, selected_caps)

# ──────────────────────────────────────────────────────────────────────────────
#  Overview Metrics 
st.subheader("Overview Metrics")
cols = st.columns(len(group_df))
for col, (grp, row) in zip(cols, group_df.iterrows()):
    # formatted capacity string (commas, parentheses if negative)
    cap_str = fmt_parenthesis(row["Capacity"])
    # numeric delta for correct arrow coloring
    delta_num = int(row["Surplus/(Deficit)"])
    col.metric(label=grp, value=cap_str, delta=delta_num)

# Main grouped table
st.subheader(f"Grouped Summary for {action.replace('_',' ').title()}")
group_fmt = group_df.copy()
for c in group_fmt.columns:
    if c != "Deficit Subtypes":
        group_fmt[c] = group_fmt[c].apply(fmt_parenthesis)
st.table(group_fmt)

# Bar chart
if st.checkbox("Show bar chart of grouped summary"):
    st.bar_chart(group_df[["Requirement","Capacity"]])

# Detailed Subtype Summary
with st.expander("Detailed Subtype Summary"):
    comp_rows = []
    for rate in selected_rates:
        base = rate.replace(RATE_SUFFIX, "")
        caps = [c for c in selected_caps if c.startswith(base)]
        cap_sum = sum(total_cap[c] for c in caps)
        req_val = total_req[rate]
        comp_rows.append({
            "Subtype": base,
            "Requirement": req_val,
            "Capacity":    cap_sum,
            "Surplus/(Deficit)": cap_sum - req_val
        })
    comp_df = pd.DataFrame(comp_rows).set_index("Subtype")
    st.table(comp_df.applymap(fmt_parenthesis))

# Raw Details
with st.expander("Raw Details (post‑count)"):
    st.markdown("**Consumption Breakdown**")
    fmt_map_req = {c:"{:,.0f}" for c in selected_rates + ["count"]}
    st.dataframe(req_detail.style.format(fmt_map_req), height=300)

    st.markdown("**Capacity Breakdown**")
    fmt_map_cap = {c:"{:,.0f}" for c in selected_caps + ["count"]}
    st.dataframe(cap_detail.style.format(fmt_map_cap), height=300)

# -- Footer with your name in bottom‐right corner
st.markdown(
    """
    <style>
      .footer {
        position: fixed;
        bottom: 10px;
        right: 10px;
        font-size: 0.8em;
        color: #888;
      }
    </style>
    <div class="footer">Created by <strong>Gary Tyler</strong></div>
    """,
    unsafe_allow_html=True,
)

