import os
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_valid_filepath(filename, fallback_name):
    if hasattr(filename, "read"):
        return filename
    path_preferred = os.path.join(BASE_DIR, filename)
    path_fallback = os.path.join(BASE_DIR, fallback_name)
    if os.path.exists(path_preferred):
        return path_preferred
    elif os.path.exists(path_fallback):
        return path_fallback
    elif os.path.exists(filename):
        return filename
    elif os.path.exists(fallback_name):
        return fallback_name
    raise FileNotFoundError(f"File {filename} not found.")

def run_reconciliation(internal_source="Internal_Orders.csv", 
                       bank_source="Bank_Settlement.csv", 
                       agreed_fee_pct=0.015, 
                       gst_pct=0.18):
    # Standard columns expected in the final reconciled table
    EXPECTED_COLUMNS = [
        "Order_ID",
        "Customer_Name",
        "Timestamp",
        "Gross_Amount",
        "Expected_Net",
        "Actual_Net",
        "Variance",
        "Audit_Status",
        "Action_Item"
    ]

    # Ingest from DataFrame or path
    if isinstance(internal_source, pd.DataFrame):
        df_internal = internal_source.copy()
    else:
        df_internal = pd.read_csv(get_valid_filepath(internal_source, "internal_orders.csv"))

    if isinstance(bank_source, pd.DataFrame):
        df_bank = bank_source.copy()
    else:
        df_bank = pd.read_csv(get_valid_filepath(bank_source, "bank_settlement.csv"))

    # If both inputs are completely empty, return an empty DataFrame with the exact schema
    if df_internal.empty and df_bank.empty:
        empty_df = pd.DataFrame(columns=EXPECTED_COLUMNS)
        empty_df["Timestamp"] = pd.to_datetime(empty_df["Timestamp"])
        return empty_df

    df_internal.columns = [c.strip().lower() for c in df_internal.columns]
    df_bank.columns = [c.strip().lower() for c in df_bank.columns]

    merged = pd.merge(df_internal, df_bank, on="order_id", how="outer", indicator=True)
    reconciled_rows = []

    for _, row in merged.iterrows():
        order_id = row["order_id"]
        merge_type = row["_merge"]
        
        # Determine fallback timestamp
        txn_date = row.get("created_at") or row.get("settled_at") or "2026-10-01 00:00:00"

        # PASS 1: MISSING SETTLEMENT
        if merge_type == "left_only":
            reconciled_rows.append({
                "Order_ID": order_id,
                "Customer_Name": row.get("customer_name", "Unknown"),
                "Timestamp": txn_date,
                "Gross_Amount": float(row.get("order_amount", 0.0)),
                "Expected_Net": None,
                "Actual_Net": 0.0,
                "Variance": round(float(row.get("order_amount", 0.0)), 2),
                "Audit_Status": "MISSING_SETTLEMENT",
                "Action_Item": "Escalate to Payment Gateway for settlement trace"
            })

        # PASS 2: PHANTOM PAYOUT
        elif merge_type == "right_only" or (merge_type == "both" and str(row.get("order_status")).upper() != "COMPLETED"):
            net_dep = float(row.get("net_deposited", 0.0))
            reconciled_rows.append({
                "Order_ID": order_id,
                "Customer_Name": row.get("customer_name", "Unknown"),
                "Timestamp": txn_date,
                "Gross_Amount": float(row.get("gross_received", 0.0)),
                "Expected_Net": 0.0,
                "Actual_Net": net_dep,
                "Variance": round(net_dep, 2),
                "Audit_Status": "PHANTOM_PAYMENT",
                "Action_Item": "Order marked failed but funds received! Fulfill or refund"
            })

        # PASS 3: DETERMINISTIC MATCH & FEE AUDIT
        elif merge_type == "both":
            gross = float(row["order_amount"])
            actual_net = float(row["net_deposited"])
            
            expected_fee = round(gross * agreed_fee_pct, 2)
            expected_tax = round(expected_fee * gst_pct, 2)
            expected_net = round(gross - (expected_fee + expected_tax), 2)
            variance = round(expected_net - actual_net, 2)

            if abs(variance) <= 0.50:
                audit_status = "RECONCILED"
                action = "Settled cleanly"
            else:
                audit_status = "FEE_OVERCHARGE"
                action = f"Overcharged by Rs. {variance:.2f}. File dispute against Gateway"

            reconciled_rows.append({
                "Order_ID": order_id,
                "Customer_Name": row.get("customer_name", "Unknown"),
                "Timestamp": txn_date,
                "Gross_Amount": gross,
                "Expected_Net": expected_net,
                "Actual_Net": actual_net,
                "Variance": variance,
                "Audit_Status": audit_status,
                "Action_Item": action
            })

    if not reconciled_rows:
        result_df = pd.DataFrame(columns=EXPECTED_COLUMNS)
    else:
        result_df = pd.DataFrame(reconciled_rows)

    result_df["Timestamp"] = pd.to_datetime(result_df["Timestamp"])
    return result_df