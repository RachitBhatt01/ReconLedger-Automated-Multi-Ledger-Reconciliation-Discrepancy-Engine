# Generate_Data.py
import pandas as pd

# Define schema structures matching internal production orders
internal_orders_df = pd.DataFrame(columns=[
    "order_id",
    "customer_name",
    "order_amount",
    "order_status",
    "created_at"
])

# Define schema structures matching payment gateway settlement statements
bank_settlement_df = pd.DataFrame(columns=[
    "settlement_id",
    "order_id",
    "gross_received",
    "fee_deducted",
    "tax_deducted",
    "net_deposited",
    "settled_at"
])

# Save empty template CSV files with headers initialized
internal_orders_df.to_csv("Internal_Orders.csv", index=False)
bank_settlement_df.to_csv("Bank_Settlement.csv", index=False)

print("Baseline CSV files initialized to 0 records.")
print("-> Internal_Orders.csv ready (0 records)")
print("-> Bank_Settlement.csv ready (0 records)")