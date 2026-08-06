import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy import text

# --- CONFIG & USERS ---
VALID_USERS = {
    "jason": "lab123",
    "rajeev": "lab123",
    "admin": "admin2026"
}

# --- CLOUD DATABASE SETUP ---
# Automatically pulls the DATABASE_URL from Streamlit Secrets
conn = st.connection("postgresql", type="sql", url=st.secrets["DATABASE_URL"])

def init_db():
    with conn.session as s:
        s.execute(text('''CREATE TABLE IF NOT EXISTS inventory
                     (name TEXT PRIMARY KEY, category TEXT, quantity INTEGER)'''))
        s.execute(text('''CREATE TABLE IF NOT EXISTS transactions
                     (id SERIAL PRIMARY KEY, 
                      timestamp TEXT, username TEXT, category TEXT, item_name TEXT, 
                      action TEXT, quantity INTEGER, project TEXT)'''))
        s.commit()

def run_query(query, params=None):
    with conn.session as s:
        s.execute(text(query), params or {})
        s.commit()

def get_data(query, params=None):
    # ttl=0 ensures the dashboard always fetches real-time stock
    return conn.query(query, params=params or {}, ttl=0)

init_db()

# --- PAGE CONFIG ---
st.set_page_config(page_title="Lab Inventory", layout="wide")

# --- LOGIN SYSTEM ---
if "current_user" not in st.session_state:
    st.session_state.current_user = None

if not st.session_state.current_user:
    st.title("🔒 Lab Inventory Login")
    with st.form("login_form"):
        username = st.text_input("Username").lower().strip()
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        
        if submitted:
            if username in VALID_USERS and VALID_USERS[username] == password:
                st.session_state.current_user = username
                st.rerun()
            else:
                st.error("Invalid username or password.")
    st.stop()

# --- MAIN DASHBOARD ---
st.title(f"🔬 Lab Inventory (Logged in as: {st.session_state.current_user.title()})")
if st.button("Logout"):
    st.session_state.current_user = None
    st.rerun()

st.divider()

tab_stock, tab_add, tab_take, tab_history = st.tabs([
    "📦 View Stock", "📥 Add/Purchase Items", "📤 Take Items", "📜 History Log"
])

# 1. VIEW STOCK TAB
with tab_stock:
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("⚡ Electronics")
        df_elec = get_data("SELECT name as \"Component\", quantity as \"Qty\" FROM inventory WHERE category='Electronics'")
        if not df_elec.empty:
            st.dataframe(df_elec, use_container_width=True, hide_index=True)
        else:
            st.info("No electronics in stock.")
            
    with col2:
        st.subheader("⚙️ Mechanical")
        df_mech = get_data("SELECT name as \"Component\", quantity as \"Qty\" FROM inventory WHERE category='Mechanical'")
        if not df_mech.empty:
            st.dataframe(df_mech, use_container_width=True, hide_index=True)
        else:
            st.info("No mechanical components in stock.")

# 2. ADD/PURCHASE ITEMS TAB
with tab_add:
    st.subheader("Add New or Restock Items")
    add_category = st.radio("Component Category:", ["Electronics", "Mechanical"], key="add_cat")
    
    with st.form("add_form"):
        add_name = st.text_input("Component Name (e.g., Arduino Nano, M3 Bolt)").strip()
        add_qty = st.number_input("Quantity Purchased/Added", min_value=1, step=1)
        add_project = st.text_input("Project / Reason")
        add_submit = st.form_submit_button("Add to Inventory")
        
        if add_submit and add_name:
            df_check = get_data("SELECT quantity FROM inventory WHERE name=:name", {"name": add_name})
            current_qty = int(df_check.iloc[0]['quantity']) if not df_check.empty else 0
            new_qty = current_qty + add_qty
            
            # Postgres UPSERT syntax
            run_query('''INSERT INTO inventory (name, category, quantity) 
                         VALUES (:name, :category, :quantity) 
                         ON CONFLICT(name) DO UPDATE SET quantity=EXCLUDED.quantity''', 
                      {"name": add_name, "category": add_category, "quantity": new_qty})
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            run_query('''INSERT INTO transactions 
                         (timestamp, username, category, item_name, action, quantity, project) 
                         VALUES (:ts, :usr, :cat, :item, :act, :qty, :proj)''',
                      {"ts": timestamp, "usr": st.session_state.current_user, "cat": add_category, 
                       "item": add_name, "act": "IN", "qty": add_qty, "proj": add_project})
            
            st.success(f"Added {add_qty} x {add_name}. Total: {new_qty}")
            st.rerun()

# 3. TAKE ITEMS TAB
with tab_take:
    st.subheader("Check Out Items")
    take_category = st.radio("Which category?", ["Electronics", "Mechanical"], key="take_cat")
    
    available_items_df = get_data("SELECT name FROM inventory WHERE category=:cat AND quantity > 0", {"cat": take_category})
    
    if available_items_df.empty:
        st.warning(f"No {take_category} items in stock.")
    else:
        with st.form("take_form"):
            take_name = st.selectbox("Select Component", available_items_df['name'].tolist())
            take_qty = st.number_input("Quantity Needed", min_value=1, step=1)
            take_project = st.text_input("Project Name (Required)")
            take_submit = st.form_submit_button("Check Out")
            
            if take_submit:
                if not take_project:
                    st.error("Please specify a project.")
                else:
                    df_check = get_data("SELECT quantity FROM inventory WHERE name=:name", {"name": take_name})
                    current_qty = int(df_check.iloc[0]['quantity'])
                    
                    if current_qty >= take_qty:
                        new_qty = current_qty - take_qty
                        run_query("UPDATE inventory SET quantity=:qty WHERE name=:name", {"qty": new_qty, "name": take_name})
                        
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        run_query('''INSERT INTO transactions 
                                     (timestamp, username, category, item_name, action, quantity, project) 
                                     VALUES (:ts, :usr, :cat, :item, :act, :qty, :proj)''',
                                  {"ts": timestamp, "usr": st.session_state.current_user, "cat": take_category, 
                                   "item": take_name, "act": "OUT", "qty": take_qty, "proj": take_project})
                        
                        st.success(f"Checked out {take_qty} x {take_name}. Remaining: {new_qty}")
                        st.rerun()
                    else:
                        st.error(f"Not enough stock! Only {current_qty} available.")

# 4. HISTORY LOG TAB
with tab_history:
    st.subheader("Lab Activity Log")
    df_history = get_data('''SELECT timestamp as "Time", username as "User", 
                             category as "Type", item_name as "Component", 
                             action as "IN/OUT", quantity as "Qty", 
                             project as "Project" 
                             FROM transactions ORDER BY id DESC''')
    st.dataframe(df_history, use_container_width=True, hide_index=True)
