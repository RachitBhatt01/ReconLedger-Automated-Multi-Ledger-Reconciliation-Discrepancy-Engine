# Testing my next GitHub commit
# added 5 second automatic records
#Created some changes: Auto reconciliation. no need to upload Internal_Orders.csv and Bank_Settlement.csv and click on Reconcliate button.
# Created some Changes: Dashboard is now dynamic, when record comes, values in database changes.
# App.py
import os
import random
import time
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
from faker import Faker

from Matcher import run_reconciliation
from Excel_Reporter import export_audit_to_excel_with_chart

fake = Faker('en_IN')

st.set_page_config(
    page_title="ReconLedger | Multi-Ledger Reconciliation Engine",
    page_icon="⚖️",
    layout="wide"
)

st.title("⚖️ ReconLedger Engine")
st.markdown("### Automated Multi-Ledger Reconciliation & Discrepancy Auditing")
st.caption("Cross-examining internal transactional ledgers against asynchronous bank settlements.")
st.divider()

# --- INITIAL STATE MANAGEMENT ---
if "internal_df" not in st.session_state or "bank_df" not in st.session_state:
    if os.path.exists("Internal_Orders.csv") and os.path.exists("Bank_Settlement.csv"):
        st.session_state["internal_df"] = pd.read_csv("Internal_Orders.csv")
        st.session_state["bank_df"] = pd.read_csv("Bank_Settlement.csv")
    else:
        st.session_state["internal_df"] = pd.DataFrame(
            columns=["order_id", "customer_name", "order_amount", "order_status", "created_at"]
        )
        st.session_state["bank_df"] = pd.DataFrame(
            columns=["settlement_id", "order_id", "gross_received", "fee_deducted", "tax_deducted", "net_deposited", "settled_at"]
        )

if "tx_counter" not in st.session_state:
    st.session_state["tx_counter"] = len(st.session_state["internal_df"])

# Helper function to append live synthetic records
def append_live_transaction(agreed_fee=0.018, gst=0.18):
    st.session_state["tx_counter"] += 1
    idx = st.session_state["tx_counter"]

    curr_time = datetime.now()
    order_id = f"ORD-LIVE-{1000 + idx}"
    settlement_id = f"SETTL-{5000 + idx}"
    gross = round(random.uniform(500.0, 45000.0), 2)
    cust = fake.name()
    timestamp_str = curr_time.strftime("%Y-%m-%d %H:%M:%S")

    rnd = random.random()
    # 75% Cleanly settled
    if rnd < 0.75:
        fee = round(gross * agreed_fee, 2)
        tax = round(fee * gst, 2)
        net = round(gross - (fee + tax), 2)
        int_row = {
            "order_id": order_id,
            "customer_name": cust,
            "order_amount": gross,
            "order_status": "COMPLETED",
            "created_at": timestamp_str
        }
        bnk_row = {
            "settlement_id": settlement_id,
            "order_id": order_id,
            "gross_received": gross,
            "fee_deducted": fee,
            "tax_deducted": tax,
            "net_deposited": net,
            "settled_at": timestamp_str
        }
    # 10% Phantom Payment (Webhook drop)
    elif rnd < 0.85:
        fee = round(gross * agreed_fee, 2)
        tax = round(fee * gst, 2)
        net = round(gross - (fee + tax), 2)
        int_row = {
            "order_id": order_id,
            "customer_name": cust,
            "order_amount": gross,
            "order_status": "CANCELLED_TIMEOUT",
            "created_at": timestamp_str
        }
        bnk_row = {
            "settlement_id": settlement_id,
            "order_id": order_id,
            "gross_received": gross,
            "fee_deducted": fee,
            "tax_deducted": tax,
            "net_deposited": net,
            "settled_at": timestamp_str
        }
    # 10% Fee Overcharge
    elif rnd < 0.95:
        over_fee = round(gross * 0.026, 2)
        over_tax = round(over_fee * gst, 2)
        shaved_net = round(gross - (over_fee + over_tax), 2)
        int_row = {
            "order_id": order_id,
            "customer_name": cust,
            "order_amount": gross,
            "order_status": "COMPLETED",
            "created_at": timestamp_str
        }
        bnk_row = {
            "settlement_id": settlement_id,
            "order_id": order_id,
            "gross_received": gross,
            "fee_deducted": over_fee,
            "tax_deducted": over_tax,
            "net_deposited": shaved_net,
            "settled_at": timestamp_str
        }
    # 5% Missing Settlement (No bank payout recorded)
    else:
        int_row = {
            "order_id": order_id,
            "customer_name": cust,
            "order_amount": gross,
            "order_status": "COMPLETED",
            "created_at": timestamp_str
        }
        bnk_row = None

    st.session_state["internal_df"] = pd.concat(
        [st.session_state["internal_df"], pd.DataFrame([int_row])],
        ignore_index=True
    )
    if bnk_row:
        st.session_state["bank_df"] = pd.concat(
            [st.session_state["bank_df"], pd.DataFrame([bnk_row])],
            ignore_index=True
        )


# --- SIDEBAR CONFIGURATION ---
st.sidebar.header("⚙️ Audit Configuration")
live_stream = st.sidebar.toggle("🔴 Enable 5s Live Data Feed", value=False)

if st.sidebar.button("🔄 Reset to 0 Records"):
    st.session_state["internal_df"] = pd.DataFrame(
        columns=["order_id", "customer_name", "order_amount", "order_status", "created_at"]
    )
    st.session_state["bank_df"] = pd.DataFrame(
        columns=["settlement_id", "order_id", "gross_received", "fee_deducted", "tax_deducted", "net_deposited", "settled_at"]
    )
    st.session_state["tx_counter"] = 0
    st.rerun()

st.sidebar.subheader("Contractual Rate Terms")
agreed_fee = st.sidebar.slider("Agreed Gateway Fee (%)", min_value=1.0, max_value=3.5, value=1.8, step=0.1) / 100
gst_rate = st.sidebar.number_input("GST on Fee (%)", min_value=0.0, max_value=28.0, value=18.0, step=1.0) / 100

# Execute Live Streaming Ingestion if active
if live_stream:
    append_live_transaction(agreed_fee, gst_rate)

# Run Reconciliation Engine
audit_df = run_reconciliation(
    internal_source=st.session_state["internal_df"],
    bank_source=st.session_state["bank_df"],
    agreed_fee_pct=agreed_fee,
    gst_pct=gst_rate
)

# --- TIMELINE RANGE FILTER (Crash-Proof Boundary Implementation) ---
st.sidebar.subheader("📅 Timeline Filter")
filtered_audit_df = audit_df

if not audit_df.empty and "Timestamp" in audit_df.columns:
    valid_dates = audit_df["Timestamp"].dropna()
    if not valid_dates.empty:
        earliest_date = valid_dates.min().date()
        latest_date = valid_dates.max().date()

        # Set calendar bounds with safety padding
        picker_min = earliest_date - timedelta(days=1)
        picker_max = latest_date + timedelta(days=1)

        date_range = st.sidebar.date_input(
            "Select Transaction Window",
            value=(earliest_date, latest_date),
            min_value=picker_min,
            max_value=picker_max
        )

        if isinstance(date_range, (tuple, list)):
            if len(date_range) == 2:
                start_dt, end_dt = date_range
                filtered_audit_df = audit_df[
                    (audit_df["Timestamp"].dt.date >= start_dt) &
                    (audit_df["Timestamp"].dt.date <= end_dt)
                ]
            elif len(date_range) == 1:
                start_dt = date_range[0]
                filtered_audit_df = audit_df[audit_df["Timestamp"].dt.date >= start_dt]
    else:
        st.sidebar.info("Awaiting timestamped transactions...")
else:
    st.sidebar.info("Awaiting incoming transactions...")

# --- TOP LEVEL FINANCIAL KPIS ---
total_records = len(filtered_audit_df)
reconciled_cnt = len(filtered_audit_df[filtered_audit_df["Audit_Status"] == "RECONCILED"]) if total_records else 0
overcharge_cnt = len(filtered_audit_df[filtered_audit_df["Audit_Status"] == "FEE_OVERCHARGE"]) if total_records else 0
phantom_cnt = len(filtered_audit_df[filtered_audit_df["Audit_Status"] == "PHANTOM_PAYMENT"]) if total_records else 0
missing_cnt = len(filtered_audit_df[filtered_audit_df["Audit_Status"] == "MISSING_SETTLEMENT"]) if total_records else 0

fee_leakage_val = filtered_audit_df[filtered_audit_df["Audit_Status"] == "FEE_OVERCHARGE"]["Variance"].sum() if total_records else 0.0
phantom_val = filtered_audit_df[filtered_audit_df["Audit_Status"] == "PHANTOM_PAYMENT"]["Actual_Net"].sum() if total_records else 0.0

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    label="✅ Cleanly Reconciled",
    value=f"{reconciled_cnt} / {total_records}",
    delta=f"{(reconciled_cnt / total_records * 100):.1f}% Match Rate" if total_records else "0.0% Match Rate"
)
col2.metric(
    label="⚠️ Fee Overcharge Leak",
    value=f"₹{fee_leakage_val:,.2f}",
    delta=f"{overcharge_cnt} Flagged",
    delta_color="inverse"
)
col3.metric(
    label="🚨 Phantom Funds",
    value=f"₹{phantom_val:,.2f}",
    delta=f"{phantom_cnt} Orders at Risk",
    delta_color="inverse"
)
col4.metric(
    label="⏳ Missing Settlements",
    value=f"{missing_cnt} Orders",
    delta="Escrow Followup",
    delta_color="inverse"
)

st.divider()

# --- FILTERABLE WORKLIST TABLE ---
st.subheader("📋 Audit Exception Worklist")

filter_choice = st.radio(
    "Filter by Status:",
    options=["ALL", "FEE_OVERCHARGE", "PHANTOM_PAYMENT", "MISSING_SETTLEMENT", "RECONCILED"],
    horizontal=True
)

if filtered_audit_df.empty:
    st.info("No records present yet. Enable the '5s Live Data Feed' in the sidebar to stream transactions live.")
else:
    if filter_choice == "ALL":
        display_df = filtered_audit_df
    else:
        display_df = filtered_audit_df[filtered_audit_df["Audit_Status"] == filter_choice]

    def highlight_status(row):
        status = row["Audit_Status"]
        if status == "RECONCILED":
            return ["background-color: rgba(46, 204, 113, 0.15)"] * len(row)
        elif status == "FEE_OVERCHARGE":
            return ["background-color: rgba(241, 196, 15, 0.15)"] * len(row)
        elif status == "PHANTOM_PAYMENT":
            return ["background-color: rgba(231, 76, 60, 0.15)"] * len(row)
        elif status == "MISSING_SETTLEMENT":
            return ["background-color: rgba(155, 89, 182, 0.15)"] * len(row)
        return [""] * len(row)

    st.dataframe(
        display_df.style.apply(highlight_status, axis=1),
        height=360
    )

# --- EXPORT REPORTING ZONE ---
st.divider()
st.subheader("📦 Audit Reports & Dispute Recovery Exports")

col_export1, col_export2 = st.columns(2)

with col_export1:
    st.markdown("#### 1. Executive Excel Audit Report")
    st.write("Generates a formal Excel workbook containing the filtered window records with an embedded native Pie Chart.")
    if not filtered_audit_df.empty:
        excel_file_data = export_audit_to_excel_with_chart(filtered_audit_df)
        st.download_button(
            label="📊 Download Excel Report (.xlsx with Circle Graph)",
            data=excel_file_data,
            file_name=f"Reconciliation_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.caption("Awaiting records to enable Excel generation.")

with col_export2:
    st.markdown("#### 2. Gateway Dispute Package")
    st.write("Exports all flagged discrepancy records (Overcharges, Phantoms, Missing Settlements) for banking claims.")
    dispute_df = filtered_audit_df[
        filtered_audit_df["Audit_Status"].isin(["FEE_OVERCHARGE", "PHANTOM_PAYMENT", "MISSING_SETTLEMENT"])
    ] if not filtered_audit_df.empty else pd.DataFrame()

    if not dispute_df.empty:
        csv_dispute = dispute_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Gateway Dispute Package (.csv)",
            data=csv_dispute,
            file_name=f"Gateway_Dispute_Claim_Package_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    else:
        st.caption("No disputed transactions detected in this window.")

# Real-time trigger loop for 5-second streaming
if live_stream:
    time.sleep(5)
    st.rerun()