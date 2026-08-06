import streamlit as st
import pandas as pd
from datetime import datetime

# --- MOCK BROWSER DATABASE SETUP ---
# Since browsers can't create real SQLite files, we use session_state for the Playground
if 'inventory' not in st.session_state:
    st.session_state.inventory = pd.DataFrame([
        {"Component": "Arduino Nano", "Category": "Electronics", "Qty": 5},
        {"Component": "M4 Bolt", "Category": "Mechanical", "Qty": 100}
    ])
if 'transactions' not in st.session_state:
    st.session_state.transactions = pd.DataFrame(columns=['Time', 'User', 'Category', 'Component', 'Action', 'Qty', 'Project'])

VALID_USERS = {"jason": "lab123", "rajeev": "lab123", "admin": "admin"}

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
                st.error("Invalid username or password. Try jason / lab123")
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

# 1. VIEW STOCK
with tab_stock:
    st.info("⚠️ This is a browser preview. Data will be erased if you refresh the page.")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("⚡ Electronics Components")
        df_elec = st.session_state.inventory[st.session_state.inventory['Category'] == 'Electronics']
        st.dataframe(df_elec, use_container_width=True, hide_index=True)
    with col2:
        st.subheader("⚙️ Mechanical Components")
        df_mech = st.session_state.inventory[st.session_state.inventory['Category'] == 'Mechanical']
        st.dataframe(df_mech, use_container_width=True, hide_index=True)

# 2. ADD ITEMS
with tab_add:
    st.subheader("Add New or Restock Items")
    add_category = st.radio("Component Category:", ["Electronics", "Mechanical"], key="add_cat")
    with st.form("add_form"):
        add_name = st.text_input("Component Name").strip()
        add_qty = st.number_input("Quantity Added", min_value=1, step=1)
        add_project = st.text_input("Project / Reason")
        add_submit = st.form_submit_button("Add to Inventory")
        
        if add_submit and add_name:
            # Update Mock Inventory
            inv = st.session_state.inventory
            if add_name in inv['Component'].values:
                inv.loc[inv['Component'] == add_name, 'Qty'] += add_qty
            else:
                new_row = pd.DataFrame([{"Component": add_name, "Category": add_category, "Qty": add_qty}])
                st.session_state.inventory = pd.concat([inv, new_row], ignore_index=True)
            
            # Log Transaction
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_log = pd.DataFrame([{"Time": timestamp, "User": st.session_state.current_user, "Category": add_category, "Component": add_name, "Action": "IN", "Qty": add_qty, "Project": add_project}])
            st.session_state.transactions = pd.concat([new_log, st.session_state.transactions], ignore_index=True)
            
            st.success(f"Added {add_qty} x {add_name}!")
            st.rerun()

# 3. TAKE ITEMS
with tab_take:
    st.subheader("Check Out Items")
    take_category = st.radio("Category:", ["Electronics", "Mechanical"], key="take_cat")
    
    available_items_df = st.session_state.inventory[(st.session_state.inventory['Category'] == take_category) & (st.session_state.inventory['Qty'] > 0)]
    
    if available_items_df.empty:
        st.warning(f"No {take_category} items in stock.")
    else:
        with st.form("take_form"):
            take_name = st.selectbox("Select Component", available_items_df['Component'].tolist())
            take_qty = st.number_input("Quantity Needed", min_value=1, step=1)
            take_project = st.text_input("Project Name (Required)")
            take_submit = st.form_submit_button("Check Out")
            
            if take_submit:
                if not take_project:
                    st.error("Please specify a project.")
                else:
                    inv = st.session_state.inventory
                    current_qty = inv.loc[inv['Component'] == take_name, 'Qty'].values[0]
                    
                    if current_qty >= take_qty:
                        inv.loc[inv['Component'] == take_name, 'Qty'] -= take_qty
                        
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        new_log = pd.DataFrame([{"Time": timestamp, "User": st.session_state.current_user, "Category": take_category, "Component": take_name, "Action": "OUT", "Qty": take_qty, "Project": take_project}])
                        st.session_state.transactions = pd.concat([new_log, st.session_state.transactions], ignore_index=True)
                        
                        st.success(f"Checked out {take_qty} x {take_name}.")
                        st.rerun()
                    else:
                        st.error(f"Not enough stock! Only {current_qty} available.")

# 4. HISTORY
with tab_history:
    st.subheader("Lab Activity Log")
    st.dataframe(st.session_state.transactions, use_container_width=True, hide_index=True)
