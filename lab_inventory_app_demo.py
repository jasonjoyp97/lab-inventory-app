import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# --- CONFIG & USERS ---
VALID_USERS = {
    "jason": "jason123",
    "ajin": "ajin",
    "admin": "admin"
}

# --- DATABASE SETUP & DEMO DATA ---
def init_db():
    conn = sqlite3.connect('lab_inventory.db')
    c = conn.cursor()
    
    # Inventory Table (Now includes 'specs')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory
                 (item_code TEXT PRIMARY KEY, name TEXT, category TEXT, specs TEXT, quantity INTEGER)''')
                 
    # Transaction Log (Now includes 'specs')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  timestamp TEXT, user TEXT, category TEXT, item_code TEXT, item_name TEXT, 
                  specs TEXT, action TEXT, quantity INTEGER, project TEXT)''')
    
    # Generate Demo Data if the database is completely empty
    c.execute("SELECT COUNT(*) FROM inventory")
    if c.fetchone()[0] == 0:
        demo_items = [
            ("ELEC-001", "Resistor", "Electronics", "10k Ohm, 0.25W, Through-Hole", 500),
            ("ELEC-002", "Capacitor", "Electronics", "10uF, 50V, Electrolytic", 200),
            ("ELEC-003", "Arduino Nano", "Electronics", "ATmega328P, 5V, Mini-B USB", 15),
            ("ELEC-004", "LED Display", "Electronics", "16x2 Character, Blue Backlight", 10),
            ("MECH-001", "Hex Nut", "Mechanical", "M3, Stainless Steel 304", 1000),
            ("MECH-002", "Allen Bolt", "Mechanical", "M4 x 12mm, Carbon Steel", 500),
            ("MECH-003", "Wooden Nail", "Mechanical", "2 inch, Galvanized", 400),
            ("MECH-004", "Clamp", "Mechanical", "C-Clamp, 2 inch opening", 20)
        ]
        c.executemany("INSERT INTO inventory VALUES (?, ?, ?, ?, ?)", demo_items)
        
        # Add an initial demo transaction
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute('''INSERT INTO transactions 
                     (timestamp, user, category, item_code, item_name, specs, action, quantity, project) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (timestamp, "admin", "Electronics", "ELEC-003", "Arduino Nano", "ATmega328P, 5V, Mini-B USB", "IN", 15, "Initial Lab Setup"))
        
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
        df_elec = get_data("SELECT item_code as 'Code', name as 'Component', specs as 'Specifications', quantity as 'Qty' FROM inventory WHERE category='Electronics'")
        if not df_elec.empty:
            st.dataframe(df_elec, use_container_width=True, hide_index=True)
        else:
            st.info("No electronics in stock.")
            
    with col2:
        st.subheader("⚙️ Mechanical")
        df_mech = get_data("SELECT item_code as 'Code', name as 'Component', specs as 'Specifications', quantity as 'Qty' FROM inventory WHERE category='Mechanical'")
        if not df_mech.empty:
            st.dataframe(df_mech, use_container_width=True, hide_index=True)
        else:
            st.info("No mechanical components in stock.")

# 2. ADD/PURCHASE ITEMS TAB
with tab_add:
    st.subheader("Add New or Restock Items")
    
    add_type = st.radio("What are you adding?", ["Restock Existing Item", "Register Brand New Item"], horizontal=True)
    add_category = st.selectbox("Component Category:", ["Electronics", "Mechanical"], key="add_cat")
    
    with st.form("add_form"):
        if add_type == "Register Brand New Item":
            input_code = st.text_input("Create Item Code (e.g., ELEC-05, MECH-12)").strip().upper()
            input_name = st.text_input("Component Name (e.g., Capacitor, Allen Bolt)").strip().title()
            
            # Dynamic specifics hint based on category
            if add_category == "Electronics":
                spec_hint = "e.g., 10uF, 50V, SMT, Through-Hole, 10k Ohm"
            else:
                spec_hint = "e.g., M4 x 10mm, Stainless Steel, 2 inch"
                
            input_specs = st.text_input(f"Specifications ({spec_hint})").strip()
            selection = None
        else:
            existing_items_df = get_data("SELECT item_code, name, specs FROM inventory WHERE category=?", (add_category,))
            if not existing_items_df.empty:
                # Combine code, name, and specs so all 3 are searchable
                options = [f"{row['item_code']} | {row['name']} | {row['specs']}" for _, row in existing_items_df.iterrows()]
                selection = st.selectbox("Search by Code, Name, or Specs (Type to search):", options)
                input_code, input_name, input_specs = None, None, None
            else:
                st.warning(f"No {add_category} items exist yet. Please register a new item.")
                selection = None
                
        add_qty = st.number_input("Quantity Purchased/Added", min_value=1, step=1)
        add_project = st.text_input("Project / Reason (e.g., General Stock, GeM Order)")
        add_submit = st.form_submit_button("Add to Inventory")
        
        if add_submit:
            # Parse variables based on mode selected
            if add_type == "Register Brand New Item":
                final_code, final_name, final_specs = input_code, input_name, input_specs
            elif selection:
                parts = selection.split(" | ")
                final_code, final_name, final_specs = parts[0], parts[1], parts[2]
            else:
                final_code, final_name, final_specs = None, None, None
            
            if final_code and final_name:
                df_check = get_data("SELECT quantity FROM inventory WHERE item_code=?", (final_code,))
                current_qty = int(df_check.iloc[0]['quantity']) if not df_check.empty else 0
                new_qty = current_qty + add_qty
                
                run_query('''INSERT INTO inventory (item_code, name, category, specs, quantity) 
                             VALUES (?, ?, ?, ?, ?) 
                             ON CONFLICT(item_code) DO UPDATE SET quantity=?''', 
                          (final_code, final_name, add_category, final_specs, new_qty, new_qty))
                
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                run_query('''INSERT INTO transactions 
                             (timestamp, user, category, item_code, item_name, specs, action, quantity, project) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                          (timestamp, st.session_state.current_user, add_category, final_code, final_name, final_specs, "IN", add_qty, add_project))
                
                st.success(f"Added {add_qty} x {final_name} ({final_code}). Total: {new_qty}")
                st.rerun()
            else:
                st.error("Please provide an Item Code, Name, and Specifications.")

# 3. TAKE ITEMS TAB
with tab_take:
    st.subheader("Check Out Items")
    take_category = st.radio("Which category?", ["Electronics", "Mechanical"], key="take_cat")
    
    available_items_df = get_data("SELECT item_code, name, specs FROM inventory WHERE category=? AND quantity > 0", (take_category,))
    
    if available_items_df.empty:
        st.warning(f"No {take_category} items currently in stock.")
    else:
        with st.form("take_form"):
            # Combine code, name, and specs for the searchable dropdown
            take_options = [f"{row['item_code']} | {row['name']} | {row['specs']}" for _, row in available_items_df.iterrows()]
            take_selection = st.selectbox("Search by Code, Name, or Specs (Type to search):", take_options)
            
            take_qty = st.number_input("Quantity Needed", min_value=1, step=1)
            take_project = st.text_input("Project Name (Required)")
            take_submit = st.form_submit_button("Check Out")
            
            if take_submit:
                if not take_project:
                    st.error("Please specify a project.")
                else:
                    parts = take_selection.split(" | ")
                    take_code, take_name, take_specs = parts[0], parts[1], parts[2]
                    
                    df_check = get_data("SELECT quantity FROM inventory WHERE item_code=?", (take_code,))
                    current_qty = int(df_check.iloc[0]['quantity'])
                    
                    if current_qty >= take_qty:
                        new_qty = current_qty - take_qty
                        run_query("UPDATE inventory SET quantity=? WHERE item_code=?", (new_qty, take_code))
                        
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        run_query('''INSERT INTO transactions 
                                     (timestamp, user, category, item_code, item_name, specs, action, quantity, project) 
                                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                  (timestamp, st.session_state.current_user, take_category, take_code, take_name, take_specs, "OUT", take_qty, take_project))
                        
                        st.success(f"Checked out {take_qty} x {take_name}. Remaining: {new_qty}")
                        st.rerun()
                    else:
                        st.error(f"Not enough stock! Only {current_qty} available.")

# 4. HISTORY LOG TAB
with tab_history:
    st.subheader("Lab Activity Log")
    df_history = get_data('''SELECT timestamp as 'Time', user as 'User', 
                             category as 'Type', item_code as 'Code', item_name as 'Component', 
                             specs as 'Specifications', action as 'IN/OUT', 
                             quantity as 'Qty', project as 'Project' 
                             FROM transactions ORDER BY id DESC''')
    st.dataframe(df_history, use_container_width=True, hide_index=True)
