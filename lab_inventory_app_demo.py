import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- CONFIG & USERS ---
VALID_USERS = {
    "jason": "lab123",
    "admin": "admin2026"
}

# --- DATABASE SETUP (SQLite) ---
def init_db():
    conn = sqlite3.connect('lab_inventory.db')
    c = conn.cursor()
    # Inventory Table now uses item_code as primary key
    c.execute('''CREATE TABLE IF NOT EXISTS inventory
                 (item_code TEXT PRIMARY KEY, name TEXT, category TEXT, quantity INTEGER)''')
    # Transaction Log now includes item_code
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  timestamp TEXT, user TEXT, category TEXT, item_code TEXT, item_name TEXT, 
                  action TEXT, quantity INTEGER, project TEXT)''')
    conn.commit()
    conn.close()

def run_query(query, params=()):
    conn = sqlite3.connect('lab_inventory.db')
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

def get_data(query, params=()):
    conn = sqlite3.connect('lab_inventory.db')
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

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
        df_elec = get_data("SELECT item_code as 'Code', name as 'Component', quantity as 'Qty' FROM inventory WHERE category='Electronics'")
        if not df_elec.empty:
            st.dataframe(df_elec, use_container_width=True, hide_index=True)
        else:
            st.info("No electronics in stock.")
            
    with col2:
        st.subheader("⚙️ Mechanical")
        df_mech = get_data("SELECT item_code as 'Code', name as 'Component', quantity as 'Qty' FROM inventory WHERE category='Mechanical'")
        if not df_mech.empty:
            st.dataframe(df_mech, use_container_width=True, hide_index=True)
        else:
            st.info("No mechanical components in stock.")

# 2. ADD/PURCHASE ITEMS TAB
with tab_add:
    st.subheader("Add New or Restock Items")
    
    # Split flow into restocking known items vs registering brand new items
    add_type = st.radio("What are you adding?", ["Restock Existing Item", "Register Brand New Item"], horizontal=True)
    add_category = st.selectbox("Component Category:", ["Electronics", "Mechanical"], key="add_cat")
    
    with st.form("add_form"):
        if add_type == "Register Brand New Item":
            # Force codes to uppercase and names to Title Case to prevent duplicates
            input_code = st.text_input("Create Item Code (e.g., ELEC-01, MECH-05)").strip().upper()
            input_name = st.text_input("Component Name (e.g., Arduino Nano)").strip().title()
            selection = None
        else:
            # Search existing items
            existing_items_df = get_data("SELECT item_code, name FROM inventory WHERE category=?", (add_category,))
            if not existing_items_df.empty:
                options = [f"{row['item_code']} | {row['name']}" for _, row in existing_items_df.iterrows()]
                selection = st.selectbox("Search by Code or Name (Type to search):", options)
                input_code = None
                input_name = None
            else:
                st.warning(f"No {add_category} items exist yet. Please register a new item.")
                selection = None
                
        add_qty = st.number_input("Quantity Purchased/Added", min_value=1, step=1)
        add_project = st.text_input("Project / Reason (e.g., General Stock, GeM Order)")
        add_submit = st.form_submit_button("Add to Inventory")
        
        if add_submit:
            # Resolve the final code and name based on the mode selected
            final_code = input_code if add_type == "Register Brand New Item" else (selection.split(" | ")[0] if selection else None)
            final_name = input_name if add_type == "Register Brand New Item" else (selection.split(" | ")[1] if selection else None)
            
            if final_code and final_name:
                df_check = get_data("SELECT quantity FROM inventory WHERE item_code=?", (final_code,))
                current_qty = int(df_check.iloc[0]['quantity']) if not df_check.empty else 0
                new_qty = current_qty + add_qty
                
                # Upsert database logic
                run_query('''INSERT INTO inventory (item_code, name, category, quantity) 
                             VALUES (?, ?, ?, ?) 
                             ON CONFLICT(item_code) DO UPDATE SET quantity=?''', 
                          (final_code, final_name, add_category, new_qty, new_qty))
                
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                run_query('''INSERT INTO transactions 
                             (timestamp, user, category, item_code, item_name, action, quantity, project) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                          (timestamp, st.session_state.current_user, add_category, final_code, final_name, "IN", add_qty, add_project))
                
                st.success(f"Added {add_qty} x {final_name} ({final_code}). Total: {new_qty}")
                st.rerun()
            else:
                st.error("Please provide both an Item Code and a Name.")

# 3. TAKE ITEMS TAB
with tab_take:
    st.subheader("Check Out Items")
    take_category = st.radio("Which category?", ["Electronics", "Mechanical"], key="take_cat")
    
    # Only fetch items that actually have stock
    available_items_df = get_data("SELECT item_code, name FROM inventory WHERE category=? AND quantity > 0", (take_category,))
    
    if available_items_df.empty:
        st.warning(f"No {take_category} items currently in stock.")
    else:
        with st.form("take_form"):
            # Combine code and name for the searchable dropdown
            take_options = [f"{row['item_code']} | {row['name']}" for _, row in available_items_df.iterrows()]
            take_selection = st.selectbox("Search by Code or Name (Type to search):", take_options)
            
            take_qty = st.number_input("Quantity Needed", min_value=1, step=1)
            take_project = st.text_input("Project Name (Required)")
            take_submit = st.form_submit_button("Check Out")
            
            if take_submit:
                if not take_project:
                    st.error("Please specify a project.")
                else:
                    take_code = take_selection.split(" | ")[0]
                    take_name = take_selection.split(" | ")[1]
                    
                    df_check = get_data("SELECT quantity FROM inventory WHERE item_code=?", (take_code,))
                    current_qty = int(df_check.iloc[0]['quantity'])
                    
                    if current_qty >= take_qty:
                        new_qty = current_qty - take_qty
                        run_query("UPDATE inventory SET quantity=? WHERE item_code=?", (new_qty, take_code))
                        
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        run_query('''INSERT INTO transactions 
                                     (timestamp, user, category, item_code, item_name, action, quantity, project) 
                                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                                  (timestamp, st.session_state.current_user, take_category, take_code, take_name, "OUT", take_qty, take_project))
                        
                        st.success(f"Checked out {take_qty} x {take_name}. Remaining: {new_qty}")
                        st.rerun()
                    else:
                        st.error(f"Not enough stock! Only {current_qty} available.")

# 4. HISTORY LOG TAB
with tab_history:
    st.subheader("Lab Activity Log")
    df_history = get_data('''SELECT timestamp as 'Time', user as 'User', 
                             category as 'Type', item_code as 'Code', item_name as 'Component', 
                             action as 'IN/OUT', quantity as 'Qty', 
                             project as 'Project' 
                             FROM transactions ORDER BY id DESC''')
    st.dataframe(df_history, use_container_width=True, hide_index=True)
