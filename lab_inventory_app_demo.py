import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timezone, timedelta
import qrcode
import io

# --- TIMEZONE SETUP ---
# Create a permanent IST timezone (+5 hours 30 mins)
IST = timezone(timedelta(hours=5, minutes=30))

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
    
    # Inventory Table 
    c.execute('''CREATE TABLE IF NOT EXISTS inventory
                 (item_code TEXT PRIMARY KEY, name TEXT, category TEXT, specs TEXT, 
                  room_no TEXT, room_name TEXT, rack_no TEXT, quantity INTEGER)''')
                 
    # Transaction Log 
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  timestamp TEXT, user TEXT, category TEXT, item_code TEXT, item_name TEXT, 
                  specs TEXT, action TEXT, quantity INTEGER, project TEXT)''')
    
    # Generate Demo Data if the database is completely empty
    c.execute("SELECT COUNT(*) FROM inventory")
    if c.fetchone()[0] == 0:
        demo_items = [
            ("ELEC-001", "Resistor", "Electronics", "10k Ohm, 0.25W, Through-Hole", "101", "Prototyping Lab", "A-1", 500),
            ("ELEC-002", "Capacitor", "Electronics", "10uF, 50V, Electrolytic", "101", "Prototyping Lab", "A-2", 200),
            ("ELEC-003", "Arduino Nano", "Electronics", "ATmega328P, 5V, Mini-B USB", "102", "Embedded Systems", "B-1", 15),
            ("ELEC-004", "LED Display", "Electronics", "16x2 Character, Blue Backlight", "102", "Embedded Systems", "B-2", 10),
            ("MECH-001", "Hex Nut", "Mechanical", "M3, Stainless Steel 304", "201", "Machine Shop", "Rack 1", 1000),
            ("MECH-002", "Allen Bolt", "Mechanical", "M4 x 12mm, Carbon Steel", "201", "Machine Shop", "Rack 1", 500),
            ("MECH-003", "Wooden Nail", "Mechanical", "2 inch, Galvanized", "205", "General Storage", "Shelf C", 400),
            ("MECH-004", "Clamp", "Mechanical", "C-Clamp, 2 inch opening", "201", "Machine Shop", "Tool Wall", 20)
        ]
        c.executemany("INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?, ?, ?)", demo_items)
        
        # Add an initial demo transaction with IST time
        timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
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

tab_stock, tab_add, tab_take, tab_edit, tab_find, tab_qr, tab_history = st.tabs([
    "📦 View Stock", "📥 Add/Purchase Items", "📤 Take Items", "✏️ Edit Items", "🔍 Find Item", "🖨️ Print Labels", "📜 History Log"
])

# 1. VIEW STOCK TAB
with tab_stock:
    st.subheader("⚡ Electronics")
    df_elec = get_data('''SELECT item_code as 'Code', name as 'Component', specs as 'Specifications', 
                          room_name || ' (' || room_no || ')' as 'Room', rack_no as 'Rack', 
                          quantity as 'Qty' FROM inventory WHERE category='Electronics' ''')
    if not df_elec.empty:
        st.dataframe(df_elec, use_container_width=True, hide_index=True)
    else:
        st.info("No electronics in stock.")
        
    st.divider()
        
    st.subheader("⚙️ Mechanical")
    df_mech = get_data('''SELECT item_code as 'Code', name as 'Component', specs as 'Specifications', 
                          room_name || ' (' || room_no || ')' as 'Room', rack_no as 'Rack', 
                          quantity as 'Qty' FROM inventory WHERE category='Mechanical' ''')
    if not df_mech.empty:
        st.dataframe(df_mech, use_container_width=True, hide_index=True)
    else:
        st.info("No mechanical components in stock.")

# 2. ADD/PURCHASE ITEMS TAB
with tab_add:
    st.subheader("Add New or Restock Items")
    
    add_type = st.radio("What are you adding?", ["Restock Existing Item", "Register Brand New Item"], horizontal=True)
    add_category = st.selectbox("Component Category:", ["Electronics", "Mechanical"], key="add_cat")
    
    with st.form("add_form", clear_on_submit=True):
        if add_type == "Register Brand New Item":
            col1, col2 = st.columns(2)
            with col1:
                input_code = st.text_input("Create Item Code (e.g., ELEC-05, MECH-12)").strip().upper()
                input_name = st.text_input("Component Name (e.g., Capacitor, Allen Bolt)").strip().title()
            with col2:
                if add_category == "Electronics":
                    spec_hint = "e.g., 10uF, 50V, SMT"
                else:
                    spec_hint = "e.g., M4 x 10mm, Stainless Steel"
                input_specs = st.text_input(f"Specifications ({spec_hint})").strip()
            
            st.write("📍 Location Details")
            loc1, loc2, loc3 = st.columns(3)
            with loc1:
                input_room_no = st.text_input("Room Number").strip()
            with loc2:
                input_room_name = st.text_input("Room Name").strip().title()
            with loc3:
                input_rack_no = st.text_input("Rack/Shelf Number").strip()
                
            selection = None
        else:
            existing_items_df = get_data("SELECT item_code, name, specs, room_no, rack_no FROM inventory WHERE category=?", (add_category,))
            if not existing_items_df.empty:
                options = [f"{row['item_code']} | {row['name']} | Loc: {row['room_no']} (Rack: {row['rack_no']})" for _, row in existing_items_df.iterrows()]
                selection = st.selectbox("Search by Code or Name (Type to search/scan):", options)
                input_code, input_name, input_specs = None, None, None
                input_room_no, input_room_name, input_rack_no = None, None, None
            else:
                st.warning(f"No {add_category} items exist yet. Please register a new item.")
                selection = None
                
        add_qty = st.number_input("Quantity Purchased/Added", min_value=1, step=1)
        add_project = st.text_input("Project / Reason (e.g., General Stock, GeM Order)")
        add_submit = st.form_submit_button("Add to Inventory")
        
        if add_submit:
            if add_type == "Register Brand New Item":
                final_code, final_name, final_specs = input_code, input_name, input_specs
                final_r_no, final_r_name, final_rack = input_room_no, input_room_name, input_rack_no
            elif selection:
                parts = selection.split(" | ")
                final_code = parts[0]
                
                existing_item = get_data("SELECT name, specs, room_no, room_name, rack_no FROM inventory WHERE item_code=?", (final_code,)).iloc[0]
                final_name, final_specs = existing_item['name'], existing_item['specs']
                final_r_no, final_r_name, final_rack = existing_item['room_no'], existing_item['room_name'], existing_item['rack_no']
            else:
                final_code, final_name, final_specs = None, None, None
            
            if final_code and final_name:
                df_check = get_data("SELECT quantity FROM inventory WHERE item_code=?", (final_code,))
                current_qty = int(df_check.iloc[0]['quantity']) if not df_check.empty else 0
                new_qty = current_qty + add_qty
                
                run_query('''INSERT INTO inventory (item_code, name, category, specs, room_no, room_name, rack_no, quantity) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?) 
                             ON CONFLICT(item_code) DO UPDATE SET quantity=?''', 
                          (final_code, final_name, add_category, final_specs, final_r_no, final_r_name, final_rack, new_qty, new_qty))
                
                timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
                run_query('''INSERT INTO transactions 
                             (timestamp, user, category, item_code, item_name, specs, action, quantity, project) 
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                          (timestamp, st.session_state.current_user, add_category, final_code, final_name, final_specs, "IN", add_qty, add_project))
                
                st.success(f"Added {add_qty} x {final_name} ({final_code}). Total: {new_qty}")
                st.rerun()
            else:
                st.error("Please provide an Item Code and Name.")

# 3. TAKE ITEMS TAB
with tab_take:
    st.subheader("Check Out Items")
    take_category = st.radio("Which category?", ["Electronics", "Mechanical"], key="take_cat")
    
    available_items_df = get_data("SELECT item_code, name, specs, room_name, rack_no FROM inventory WHERE category=? AND quantity > 0", (take_category,))
    
    if available_items_df.empty:
        st.warning(f"No {take_category} items currently in stock.")
    else:
        with st.form("take_form", clear_on_submit=True):
            take_options = [f"{row['item_code']} | {row['name']} | Loc: {row['room_name']} ({row['rack_no']})" for _, row in available_items_df.iterrows()]
            take_selection = st.selectbox("Search by Code, Name, or Location (Type to search/scan):", take_options)
            
            take_qty = st.number_input("Quantity Needed", min_value=1, step=1)
            take_project = st.text_input("Project Name (Required)")
            take_submit = st.form_submit_button("Check Out")
            
            if take_submit:
                if not take_project:
                    st.error("Please specify a project.")
                else:
                    take_code = take_selection.split(" | ")[0]
                    
                    item_details = get_data("SELECT name, specs, quantity FROM inventory WHERE item_code=?", (take_code,)).iloc[0]
                    take_name = item_details['name']
                    take_specs = item_details['specs']
                    current_qty = int(item_details['quantity'])
                    
                    if current_qty >= take_qty:
                        new_qty = current_qty - take_qty
                        run_query("UPDATE inventory SET quantity=? WHERE item_code=?", (new_qty, take_code))
                        
                        timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
                        run_query('''INSERT INTO transactions 
                                     (timestamp, user, category, item_code, item_name, specs, action, quantity, project) 
                                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                  (timestamp, st.session_state.current_user, take_category, take_code, take_name, take_specs, "OUT", take_qty, take_project))
                        
                        st.success(f"Checked out {take_qty} x {take_name}. Remaining: {new_qty}")
                        st.rerun()
                    else:
                        st.error(f"Not enough stock! Only {current_qty} available.")

# 4. EDIT ITEMS TAB
with tab_edit:
    st.subheader("Edit Item Details & Location")
    edit_category = st.radio("Select Category:", ["Electronics", "Mechanical"], key="edit_cat", horizontal=True)
    
    existing_items_df = get_data("SELECT item_code, name, specs, room_no, room_name, rack_no FROM inventory WHERE category=?", (edit_category,))
    
    if existing_items_df.empty:
        st.warning(f"No {edit_category} items exist yet.")
    else:
        edit_options = [f"{row['item_code']} | {row['name']} | Loc: {row['room_name']}" for _, row in existing_items_df.iterrows()]
        edit_selection = st.selectbox("Select Item to Edit:", edit_options)
        
        current_code = edit_selection.split(" | ")[0]
        current_data = existing_items_df[existing_items_df['item_code'] == current_code].iloc[0]
        
        with st.form("edit_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("Component Name", value=current_data['name']).strip().title()
                new_specs = st.text_input("Specifications", value=current_data['specs']).strip()
            with col2:
                new_room_no = st.text_input("Room Number", value=current_data['room_no']).strip()
                new_room_name = st.text_input("Room Name", value=current_data['room_name']).strip().title()
                new_rack_no = st.text_input("Rack/Shelf Number", value=current_data['rack_no']).strip()
            
            submit_edit = st.form_submit_button("Update Item Details")
            
            if submit_edit:
                if not new_name:
                    st.error("Name cannot be empty.")
                else:
                    run_query('''UPDATE inventory 
                                 SET name=?, specs=?, room_no=?, room_name=?, rack_no=? 
                                 WHERE item_code=?''', 
                              (new_name, new_specs, new_room_no, new_room_name, new_rack_no, current_code))
                    run_query("UPDATE transactions SET item_name=?, specs=? WHERE item_code=?", (new_name, new_specs, current_code))
                    
                    st.success(f"Successfully updated {current_code}!")
                    st.rerun()

# 5. FIND ITEM TAB
with tab_find:
    st.subheader("🔍 Find Component Location")
    search_query = st.text_input("Search by Name, Code, or Specifications (e.g., 'Arduino', '10uF', 'ELEC-003')").strip()
    
    if search_query:
        query_param = f"%{search_query}%"
        results_df = get_data('''SELECT item_code as 'Code', name as 'Component', 
                                 category as 'Category', specs as 'Specifications', 
                                 room_name || ' (' || room_no || ')' as 'Room', 
                                 rack_no as 'Rack', quantity as 'Qty' 
                                 FROM inventory 
                                 WHERE name LIKE ? OR item_code LIKE ? OR specs LIKE ?''', 
                              (query_param, query_param, query_param))
        
        if not results_df.empty:
            st.success(f"Found {len(results_df)} matching item(s):")
            st.dataframe(results_df, use_container_width=True, hide_index=True)
        else:
            st.warning("No items found matching your search.")

# 6. QR CODE LABELS TAB
with tab_qr:
    st.subheader("🖨️ Generate QR Code Labels")
    st.write("Scan these printed labels with your phone camera to instantly view the component details, or use a USB scanner to rapidly fill forms.")
    
    # Updated SQL to also fetch 'specs' for the QR payload
    all_items_df = get_data("SELECT item_code, name, specs, room_name, rack_no FROM inventory")
    
    if all_items_df.empty:
        st.warning("No items in inventory to generate labels for.")
    else:
        qr_options = [f"{row['item_code']} | {row['name']} | Loc: {row['room_name']} ({row['rack_no']})" for _, row in all_items_df.iterrows()]
        qr_selection = st.selectbox("Select Component for Label:", qr_options)
        
        if st.button("Generate QR Code"):
            qr_code_text = qr_selection.split(" | ")[0]
            
            # Fetch the specific row details
            item_data = all_items_df[all_items_df['item_code'] == qr_code_text].iloc[0]
            qr_item_name = item_data['name']
            qr_item_specs = item_data['specs']
            
            # Create a detailed multi-line payload for the QR code
            detailed_qr_data = f"Code: {qr_code_text}\nItem: {qr_item_name}\nSpecs: {qr_item_specs}"
            
            # Generate QR code
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(detailed_qr_data)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Save to buffer for Streamlit to render
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            
            col1, col2 = st.columns([1, 2])
            with col1:
                st.image(buf, caption=f"{qr_item_name} ({qr_code_text})", width=200)
            with col2:
                st.success("QR Code Generated successfully!")
                st.download_button(
                    label="📥 Download QR Image",
                    data=buf.getvalue(),
                    file_name=f"{qr_code_text}_label.png",
                    mime="image/png"
                )

# 7. HISTORY LOG TAB
with tab_history:
    st.subheader("Lab Activity Log")
    df_history = get_data('''SELECT 
                             DATE(timestamp) as 'Date',
                             TIME(timestamp) as 'Time (IST)',
                             user as 'User', 
                             category as 'Type', item_code as 'Code', item_name as 'Component', 
                             specs as 'Specifications', action as 'IN/OUT', 
                             quantity as 'Qty', project as 'Project' 
                             FROM transactions ORDER BY id DESC''')
    st.dataframe(df_history, use_container_width=True, hide_index=True)
