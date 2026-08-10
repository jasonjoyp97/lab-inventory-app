import streamlit as st
import psycopg2
import pandas as pd
from datetime import datetime, timezone, timedelta
import qrcode
import io
import os
import urllib.request
from PIL import Image, ImageDraw, ImageFont
import hashlib

# --- TIMEZONE SETUP ---
IST = timezone(timedelta(hours=5, minutes=30))

# --- SECURITY HELPER FUNCTIONS ---
def hash_password(password):
    """Encrypts the password before saving to the database"""
    return hashlib.sha256(str.encode(password)).hexdigest()

def verify_password(provided_password, stored_hash):
    """Checks if the provided password matches the database hash"""
    return hash_password(provided_password) == stored_hash

# --- DATABASE CONNECTION ENGINE ---
def get_db_connection():
    try:
        db_url = st.secrets["DATABASE_URL"]
        return psycopg2.connect(db_url)
    except KeyError:
        st.error("⚠️ PostgreSQL connection string not found! Please check your Streamlit Secrets.")
        st.stop()
    except Exception as e:
        st.error(f"⚠️ Failed to connect to database: {e}")
        st.stop()

def run_query(query, params=()):
    conn = get_db_connection()
    with conn.cursor() as c:
        c.execute(query, params)
    conn.commit()
    conn.close()

def get_data(query, params=()):
    conn = get_db_connection()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

# --- DATABASE SETUP ---
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. Inventory Table
    c.execute('''CREATE TABLE IF NOT EXISTS inventory
                 (item_code TEXT PRIMARY KEY, name TEXT, category TEXT, specs TEXT, 
                  room_no TEXT, room_name TEXT, rack_no TEXT, quantity INTEGER, 
                  low_stock_threshold INTEGER, image BYTEA)''')
                 
    # 2. Transaction Log
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id SERIAL PRIMARY KEY, 
                  timestamp TEXT, user_name TEXT, category TEXT, item_code TEXT, item_name TEXT, 
                  specs TEXT, action TEXT, quantity INTEGER, project TEXT)''')
                  
    # 3. User Accounts Table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT, role TEXT, status TEXT)''')

    # 4. Restock Notes (Messaging System) Table
    c.execute('''CREATE TABLE IF NOT EXISTS restock_notes
                 (id SERIAL PRIMARY KEY, timestamp TEXT, user_name TEXT, 
                  item_code TEXT, item_name TEXT, message TEXT)''')
    
    # Create the Master Admin account if the table is empty
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        admin_hash = hash_password("admin")
        c.execute("INSERT INTO users (username, password, role, status) VALUES (%s, %s, %s, %s)", 
                  ('admin', admin_hash, 'admin', 'approved'))
        
    conn.commit()
    conn.close()

# --- PAGE CONFIG ---
st.set_page_config(page_title="Lab Inventory", layout="wide")
init_db()

# --- STATE MANAGEMENT ---
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "current_role" not in st.session_state:
    st.session_state.current_role = None
if "low_stock_alerted" not in st.session_state:
    st.session_state.low_stock_alerted = False

# --- LOGIN & REGISTRATION SYSTEM ---
if not st.session_state.current_user:
    st.title("🔬 Lab Inventory Portal")
    
    tab_login, tab_signup = st.tabs(["🔒 Login", "📝 Request Access"])
    
    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Username").lower().strip()
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            
            if submitted:
                if not username or not password:
                    st.error("Please enter both username and password.")
                else:
                    user_df = get_data("SELECT password, role, status FROM users WHERE username = %s", (username,))
                    if not user_df.empty:
                        stored_hash = user_df.iloc[0]['password']
                        status = user_df.iloc[0]['status']
                        role = user_df.iloc[0]['role']
                        
                        if verify_password(password, stored_hash):
                            if status == 'approved':
                                st.session_state.current_user = username
                                st.session_state.current_role = role
                                st.session_state.low_stock_alerted = False # Reset alert trigger for new login
                                st.rerun()
                            else:
                                st.warning("Your account is pending approval from the Admin.")
                        else:
                            st.error("Invalid username or password.")
                    else:
                        st.error("Invalid username or password.")
                        
    with tab_signup:
        with st.form("signup_form", clear_on_submit=True):
            st.write("Submit your details to the Admin for approval.")
            new_user = st.text_input("Desired Username").lower().strip()
            new_pass = st.text_input("Create Password", type="password")
            confirm_pass = st.text_input("Confirm Password", type="password")
            signup_submitted = st.form_submit_button("Request Account")
            
            if signup_submitted:
                if not new_user or not new_pass:
                    st.error("All fields are required.")
                elif new_pass != confirm_pass:
                    st.error("Passwords do not match.")
                else:
                    check_user = get_data("SELECT username FROM users WHERE username = %s", (new_user,))
                    if not check_user.empty:
                        st.error("Username already exists. Please choose another.")
                    else:
                        run_query("INSERT INTO users (username, password, role, status) VALUES (%s, %s, 'user', 'pending')", 
                                  (new_user, hash_password(new_pass)))
                        st.success("Access requested successfully! Please wait for Admin approval.")
    st.stop()

# --- SIDEBAR: USER SETTINGS & ADMIN PANEL ---
with st.sidebar:
    st.header(f"👤 {st.session_state.current_user.title()}")
    st.caption(f"Role: {st.session_state.current_role.title()}")
    st.divider()
    
    with st.expander("🔑 Change My Password"):
        with st.form("change_pw_form", clear_on_submit=True):
            old_pw = st.text_input("Current Password", type="password")
            new_pw = st.text_input("New Password", type="password")
            update_pw_btn = st.form_submit_button("Update Password")
            
            if update_pw_btn:
                user_data = get_data("SELECT password FROM users WHERE username=%s", (st.session_state.current_user,))
                if verify_password(old_pw, user_data.iloc[0]['password']):
                    run_query("UPDATE users SET password=%s WHERE username=%s", (hash_password(new_pw), st.session_state.current_user))
                    st.success("Password updated!")
                else:
                    st.error("Current password incorrect.")
    
    if st.session_state.current_role == 'admin':
        with st.expander("👑 Manage Users", expanded=True):
            st.write("**Pending Approvals**")
            pending_users = get_data("SELECT username FROM users WHERE status='pending'")
            if pending_users.empty:
                st.info("No pending requests.")
            else:
                for idx, row in pending_users.iterrows():
                    col1, col2 = st.columns([2, 1])
                    col1.write(row['username'])
                    if col2.button("Approve", key=f"app_{row['username']}"):
                        run_query("UPDATE users SET status='approved' WHERE username=%s", (row['username'],))
                        st.rerun()
            
            st.divider()
            st.write("**Active Users**")
            active_users = get_data("SELECT username FROM users WHERE status='approved' AND role!='admin'")
            if not active_users.empty:
                user_to_delete = st.selectbox("Select User to Remove", active_users['username'].tolist())
                if st.button("Delete User", type="primary"):
                    run_query("DELETE FROM users WHERE username=%s", (user_to_delete,))
                    st.success(f"Removed {user_to_delete}")
                    st.rerun()
            else:
                st.info("No other active users.")
                
    st.divider()
    if st.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# --- LOW STOCK LOGIN POPUP ALERT ---
if not st.session_state.low_stock_alerted:
    # Check the database for low stock items just once when they log in
    low_stock_count_df = get_data("SELECT COUNT(*) FROM inventory WHERE quantity <= low_stock_threshold")
    low_stock_count = int(low_stock_count_df.iloc[0, 0])
    
    if low_stock_count > 0:
        # Fires a toast notification in the bottom right corner
        st.toast(f"🚨 **Warning:** {low_stock_count} item(s) are currently running low on stock! Check the 'Low Stock' tab.", icon="⚠️")
    
    st.session_state.low_stock_alerted = True

# --- MAIN DASHBOARD ---
st.title("🔬 Lab Inventory Management")

tab_stock, tab_add, tab_take, tab_edit, tab_find, tab_qr, tab_warning, tab_history = st.tabs([
    "📦 View Stock", "📥 Add Items", "📤 Take Items", "✏️ Edit Items", "🔍 Find", "🖨️ Labels", "⚠️ Low Stock", "📜 History"
])

# 1. VIEW STOCK TAB
with tab_stock:
    st.subheader("⚡ Electronics")
    df_elec = get_data('''SELECT item_code as "Code", name as "Component", specs as "Specifications", 
                          room_name || ' (' || room_no || ')' as "Room", rack_no as "Rack", 
                          quantity as "Qty", low_stock_threshold as "Warning Lvl" FROM inventory WHERE category='Electronics' ''')
    if not df_elec.empty:
        st.dataframe(df_elec, use_container_width=True, hide_index=True)
    else:
        st.info("No electronics in stock.")
        
    st.divider()
        
    st.subheader("⚙️ Mechanical")
    df_mech = get_data('''SELECT item_code as "Code", name as "Component", specs as "Specifications", 
                          room_name || ' (' || room_no || ')' as "Room", rack_no as "Rack", 
                          quantity as "Qty", low_stock_threshold as "Warning Lvl" FROM inventory WHERE category='Mechanical' ''')
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
                    spec_hint = "e.g., 10uF, 50V"
                    input_specs = st.text_input(f"Specifications ({spec_hint})").strip()
                    mounting_type = st.radio("Mounting Type", ["None", "SMT", "Through-Hole"], horizontal=True)
                    input_threshold = st.number_input("Low Stock Warning Level", min_value=1, step=1, value=10)
                else:
                    spec_hint = "e.g., M4 x 10mm, Stainless Steel"
                    input_specs = st.text_input(f"Specifications ({spec_hint})").strip()
                    mounting_type = "None"
                    input_threshold = st.number_input("Low Stock Warning Level", min_value=1, step=1, value=10)
            
            st.write("📍 Location & Image Details")
            loc1, loc2, loc3 = st.columns(3)
            with loc1:
                input_room_no = st.text_input("Room Number").strip()
            with loc2:
                input_room_name = st.text_input("Room Name").strip().title()
            with loc3:
                input_rack_no = st.text_input("Rack/Shelf Number").strip()
                
            input_image = st.file_uploader("Upload Component Picture (Optional)", type=['png', 'jpg', 'jpeg'])
                
            selection = None
        else:
            existing_items_df = get_data("SELECT item_code, name, specs, room_no, rack_no, low_stock_threshold FROM inventory WHERE category=%s", (add_category,))
            if not existing_items_df.empty:
                options = [f"{row['item_code']} | {row['name']} | Loc: {row['room_no']} (Rack: {row['rack_no']})" for _, row in existing_items_df.iterrows()]
                selection = st.selectbox("Search by Code or Name (Type to search/scan):", options)
                input_code, input_name, input_specs = None, None, None
                input_room_no, input_room_name, input_rack_no, input_threshold, input_image = None, None, None, None, None
            else:
                st.warning(f"No {add_category} items exist yet. Please register a new item.")
                selection = None
                
        add_qty = st.number_input("Quantity Purchased/Added", min_value=1, step=1)
        add_project = st.text_input("Project / Reason (e.g., General Stock, GeM Order)")
        add_submit = st.form_submit_button("Add to Inventory")
        
        if add_submit:
            if add_type == "Register Brand New Item":
                final_specs = input_specs
                if mounting_type != "None":
                    final_specs = f"{input_specs} [{mounting_type}]" if input_specs else f"[{mounting_type}]"
                
                final_code, final_name = input_code, input_name
                final_r_no, final_r_name, final_rack = input_room_no, input_room_name, input_rack_no
                final_threshold = input_threshold
                final_img_bytes = input_image.getvalue() if input_image is not None else None
            elif selection:
                parts = selection.split(" | ")
                final_code = parts[0]
                
                existing_item = get_data("SELECT name, specs, room_no, room_name, rack_no, low_stock_threshold, image FROM inventory WHERE item_code=%s", (final_code,)).iloc[0]
                final_name, final_specs = existing_item['name'], existing_item['specs']
                final_r_no, final_r_name, final_rack = existing_item['room_no'], existing_item['room_name'], existing_item['rack_no']
                final_threshold = existing_item['low_stock_threshold']
                final_img_bytes = existing_item['image']
            else:
                final_code, final_name, final_specs = None, None, None
            
            if final_code and final_name:
                df_check = get_data("SELECT quantity FROM inventory WHERE item_code=%s", (final_code,))
                current_qty = int(df_check.iloc[0]['quantity']) if not df_check.empty else 0
                new_qty = current_qty + add_qty
                
                run_query('''INSERT INTO inventory (item_code, name, category, specs, room_no, room_name, rack_no, quantity, low_stock_threshold, image) 
                             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) 
                             ON CONFLICT (item_code) DO UPDATE SET quantity=%s''', 
                          (final_code, final_name, add_category, final_specs, final_r_no, final_r_name, final_rack, new_qty, final_threshold, final_img_bytes, new_qty))
                
                timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
                run_query('''INSERT INTO transactions 
                             (timestamp, user_name, category, item_code, item_name, specs, action, quantity, project) 
                             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                          (timestamp, st.session_state.current_user, add_category, final_code, final_name, final_specs, "IN", add_qty, add_project))
                
                st.success(f"Added {add_qty} x {final_name} ({final_code}). Total: {new_qty}")
                st.rerun()
            else:
                st.error("Please provide an Item Code and Name.")

# 3. TAKE ITEMS TAB
with tab_take:
    st.subheader("Check Out Items")
    take_category = st.radio("Which category?", ["Electronics", "Mechanical"], key="take_cat")
    
    available_items_df = get_data("SELECT item_code, name, specs, room_name, rack_no FROM inventory WHERE category=%s AND quantity > 0", (take_category,))
    
    if available_items_df.empty:
        st.warning(f"No {take_category} items currently in stock.")
    else:
        take_options = [f"{row['item_code']} | {row['name']} | Loc: {row['room_name']} ({row['rack_no']})" for _, row in available_items_df.iterrows()]
        take_selection = st.selectbox("Search by Code, Name, or Location (Type to search/scan):", take_options)
        take_code = take_selection.split(" | ")[0]
        
        preview_data = get_data("SELECT image, quantity, name, specs FROM inventory WHERE item_code=%s", (take_code,)).iloc[0]
        
        col1, col2 = st.columns([1, 2])
        with col1:
            if preview_data['image'] is not None:
                st.image(bytes(preview_data['image']), caption="Reference Image", use_container_width=True)
            else:
                st.info("📷 No picture available for this item.")
        
        with col2:
            st.write(f"**Current Stock:** {preview_data['quantity']}")
            st.write(f"**Specifications:** {preview_data['specs']}")
            
            with st.form("take_form", clear_on_submit=True):
                take_qty = st.number_input("Quantity Needed", min_value=1, max_value=int(preview_data['quantity']), step=1)
                take_project = st.text_input("Project Name (Required)")
                take_submit = st.form_submit_button("Check Out")
                
                if take_submit:
                    if not take_project:
                        st.error("Please specify a project.")
                    else:
                        new_qty = int(preview_data['quantity']) - take_qty
                        run_query("UPDATE inventory SET quantity=%s WHERE item_code=%s", (new_qty, take_code))
                        
                        timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
                        run_query('''INSERT INTO transactions 
                                     (timestamp, user_name, category, item_code, item_name, specs, action, quantity, project) 
                                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                                  (timestamp, st.session_state.current_user, take_category, take_code, preview_data['name'], preview_data['specs'], "OUT", take_qty, take_project))
                        
                        st.success(f"Checked out {take_qty} x {preview_data['name']}. Remaining: {new_qty}")
                        st.rerun()

# 4. EDIT ITEMS TAB
with tab_edit:
    st.subheader("Edit Item Details & Location")
    edit_category = st.radio("Select Category:", ["Electronics", "Mechanical"], key="edit_cat", horizontal=True)
    
    existing_items_df = get_data("SELECT item_code, name, specs, room_no, room_name, rack_no, low_stock_threshold, image FROM inventory WHERE category=%s", (edit_category,))
    
    if existing_items_df.empty:
        st.warning(f"No {edit_category} items exist yet.")
    else:
        edit_options = [f"{row['item_code']} | {row['name']} | Loc: {row['room_name']}" for _, row in existing_items_df.iterrows()]
        edit_selection = st.selectbox("Select Item to Edit:", edit_options)
        
        current_code = edit_selection.split(" | ")[0]
        current_data = existing_items_df[existing_items_df['item_code'] == current_code].iloc[0]
        
        if current_data['image'] is not None:
            st.image(bytes(current_data['image']), width=150, caption="Current Picture")
            
        with st.form("edit_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("Component Name", value=current_data['name']).strip().title()
                new_specs = st.text_input("Specifications", value=current_data['specs']).strip()
                new_threshold = st.number_input("Low Stock Warning Level", value=int(current_data['low_stock_threshold']), min_value=1, step=1)
            with col2:
                new_room_no = st.text_input("Room Number", value=current_data['room_no']).strip()
                new_room_name = st.text_input("Room Name", value=current_data['room_name']).strip().title()
                new_rack_no = st.text_input("Rack/Shelf Number", value=current_data['rack_no']).strip()
                
            new_image = st.file_uploader("Upload New Picture (Leave empty to keep current picture)", type=['png', 'jpg', 'jpeg'])
            
            submit_edit = st.form_submit_button("Update Item Details")
            
            if submit_edit:
                if not new_name:
                    st.error("Name cannot be empty.")
                else:
                    if new_image is not None:
                        img_bytes = new_image.getvalue()
                        run_query('''UPDATE inventory 
                                     SET name=%s, specs=%s, room_no=%s, room_name=%s, rack_no=%s, low_stock_threshold=%s, image=%s 
                                     WHERE item_code=%s''', 
                                  (new_name, new_specs, new_room_no, new_room_name, new_rack_no, new_threshold, img_bytes, current_code))
                    else:
                        run_query('''UPDATE inventory 
                                     SET name=%s, specs=%s, room_no=%s, room_name=%s, rack_no=%s, low_stock_threshold=%s 
                                     WHERE item_code=%s''', 
                                  (new_name, new_specs, new_room_no, new_room_name, new_rack_no, new_threshold, current_code))
                                  
                    run_query("UPDATE transactions SET item_name=%s, specs=%s WHERE item_code=%s", (new_name, new_specs, current_code))
                    
                    st.success(f"Successfully updated {current_code}!")
                    st.rerun()

# 5. FIND ITEM TAB
with tab_find:
    st.subheader("🔍 Find Component Location")
    search_query = st.text_input("Search by Name, Code, or Specifications (e.g., 'Arduino', '10uF', 'ELEC-003')").strip()
    
    if search_query:
        query_param = f"%{search_query}%"
        results_df = get_data('''SELECT item_code as "Code", name as "Component", 
                                 category as "Category", specs as "Specifications", 
                                 room_name || ' (' || room_no || ')' as "Room", 
                                 rack_no as "Rack", quantity as "Qty", image 
                                 FROM inventory 
                                 WHERE name ILIKE %s OR item_code ILIKE %s OR specs ILIKE %s''', 
                              (query_param, query_param, query_param))
        
        if not results_df.empty:
            st.success(f"Found {len(results_df)} matching item(s):")
            for idx, row in results_df.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns([1, 4])
                    with c1:
                        if row['image'] is not None:
                            st.image(bytes(row['image']), use_container_width=True)
                        else:
                            st.info("No Image")
                    with c2:
                        st.write(f"### {row['Component']} ({row['Code']})")
                        st.write(f"**Specs:** {row['Specifications']}")
                        st.write(f"**Location:** Room {row['Room']} | **Rack:** {row['Rack']}")
                        st.write(f"**Current Stock:** {row['Qty']} units")
        else:
            st.warning("No items found matching your search.")

# 6. QR CODE LABELS TAB
with tab_qr:
    st.subheader("🖨️ Generate QR Code Labels")
    st.write("Scan these printed labels with your phone camera to instantly view the component details, or use a USB scanner to rapidly fill forms.")
    
    all_items_df = get_data("SELECT item_code, name, specs, room_name, rack_no FROM inventory")
    
    if all_items_df.empty:
        st.warning("No items in inventory to generate labels for.")
    else:
        qr_options = [f"{row['item_code']} | {row['name']} | Loc: {row['room_name']} ({row['rack_no']})" for _, row in all_items_df.iterrows()]
        qr_selection = st.selectbox("Select Component for Label:", qr_options)
        
        if st.button("Generate QR Code"):
            qr_code_text = qr_selection.split(" | ")[0]
            
            item_data = all_items_df[all_items_df['item_code'] == qr_code_text].iloc[0]
            qr_item_name = item_data['name']
            qr_item_specs = item_data['specs']
            qr_rack_no = item_data['rack_no']
            
            detailed_qr_data = f"Code: {qr_code_text}\nItem: {qr_item_name}\nSpecs: {qr_item_specs}"
            
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(detailed_qr_data)
            qr.make(fit=True)
            
            qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
            qr_w, qr_h = qr_img.size
            
            text_margin = 100 
            label_img = Image.new('RGB', (qr_w, qr_h + text_margin), 'white')
            label_img.paste(qr_img, (0, text_margin))
            
            draw = ImageDraw.Draw(label_img)
            
            font_path = "OpenSans-Bold.ttf"
            if not os.path.exists(font_path):
                try:
                    urllib.request.urlretrieve("https://github.com/googlefonts/opensans/raw/main/fonts/ttf/OpenSans-Bold.ttf", font_path)
                except Exception:
                    pass
            
            try:
                font = ImageFont.truetype(font_path, 50)
            except IOError:
                font = ImageFont.load_default() 
            
            label_text = f"RACK: {qr_rack_no}"
            
            try:
                left, top, right, bottom = draw.textbbox((0, 0), label_text, font=font)
                text_w = right - left
                text_h = bottom - top
            except AttributeError:
                text_w, text_h = draw.textsize(label_text, font=font)
                
            x_pos = (qr_w - text_w) // 2
            y_pos = 20
            
            draw.text((x_pos, y_pos), label_text, font=font, fill="black")
            
            buf = io.BytesIO()
            label_img.save(buf, format="PNG")
            
            col1, col2 = st.columns([1, 2])
            with col1:
                st.image(buf, caption=f"{qr_item_name} ({qr_code_text})", width=250)
            with col2:
                st.success("QR Code Generated successfully!")
                st.download_button(
                    label="📥 Download QR Label",
                    data=buf.getvalue(),
                    file_name=f"{qr_code_text}_label.png",
                    mime="image/png"
                )

# 7. LOW STOCK WARNING TAB
with tab_warning:
    st.subheader("⚠️ Low Stock Alerts")
    st.write("Components that have dropped to or below their warning threshold.")
    
    df_warning = get_data('''SELECT item_code as "Code", name as "Component", category as "Category", 
                             quantity as "Current Qty", low_stock_threshold as "Warning Level", 
                             room_name || ' (' || rack_no || ')' as "Location" 
                             FROM inventory WHERE quantity <= low_stock_threshold ORDER BY category, name''')
    
    if not df_warning.empty:
        st.error(f"Attention: {len(df_warning)} item(s) are running low and need to be reordered.")
        st.dataframe(df_warning, use_container_width=True, hide_index=True)
        
        csv_data = df_warning.to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label="📄 Download Reorder List (CSV)",
            data=csv_data,
            file_name=f"Low_Stock_Reorder_List_{datetime.now(IST).strftime('%Y-%m-%d')}.csv",
            mime="text/csv",
        )
    else:
        st.success("✅ All items are sufficiently stocked! No warnings to display.")

    st.divider()

    # --- NEW FEATURE: RESTOCK COMMUNICATION BOARD ---
    st.subheader("💬 Restock Coordination")
    st.write("Leave notes for your lab mates about reordering low stock components.")
    
    col_chat, col_form = st.columns([1.5, 1])
    
    with col_chat:
        st.write("**Recent Notes:**")
        # Fetch the last 20 messages securely
        notes_df = get_data("SELECT timestamp, user_name, item_name, message FROM restock_notes ORDER BY id DESC LIMIT 20")
        
        if not notes_df.empty:
            for _, row in notes_df.iterrows():
                # Display messages beautifully with user and item context
                st.info(f"👤 **{row['user_name'].title()}** ({row['timestamp']})\n\n📦 **{row['item_name']}:** {row['message']}")
        else:
            st.write("No notes have been posted yet.")
            
    with col_form:
        if not df_warning.empty:
            with st.form("add_note_form", clear_on_submit=True):
                st.write("**Add a Note**")
                # Create dropdown options restricted only to items currently low on stock
                note_options = [f"{row['Code']} | {row['Component']}" for _, row in df_warning.iterrows()]
                selected_note_item = st.selectbox("Select Low Component", note_options)
                
                # Input field for the message
                note_msg = st.text_input("Message (e.g., 'Will order on GeM tomorrow', 'Found 10 extras in a drawer')")
                submit_note = st.form_submit_button("Post Note")
                
                if submit_note:
                    if note_msg.strip() == "":
                        st.error("Message cannot be empty.")
                    else:
                        item_c = selected_note_item.split(" | ")[0]
                        item_n = selected_note_item.split(" | ")[1]
                        now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
                        
                        run_query("INSERT INTO restock_notes (timestamp, user_name, item_code, item_name, message) VALUES (%s, %s, %s, %s, %s)", 
                                  (now, st.session_state.current_user, item_c, item_n, note_msg))
                        st.rerun()
        else:
            st.info("Stock levels are healthy. No items require coordination.")

# 8. HISTORY LOG TAB
with tab_history:
    st.subheader("Lab Activity Log")
    
    # --- NEW FEATURE: ADMIN HISTORY MANAGEMENT ---
    if st.session_state.current_role == 'admin':
        with st.expander("🛠️ Admin Tools: Manage History", expanded=False):
            st.warning("⚠️ **Note:** Deleting a log here only removes the text record. It DOES NOT reverse the physical stock quantity. Use 'Edit Items' to fix actual stock levels.")
            
            col1, col2 = st.columns([2, 1])
            with col1:
                del_id = st.number_input("Enter Log ID to Delete:", min_value=1, step=1)
            with col2:
                st.write("") # Vertical spacing alignment
                st.write("")
                if st.button("Delete Single Record", type="primary"):
                    run_query("DELETE FROM transactions WHERE id=%s", (del_id,))
                    st.success(f"Record #{del_id} deleted.")
                    st.rerun()
            
            st.divider()
            
            # The "Nuclear Option" for when testing is done
            if st.button("🚨 Clear ALL History (Prepare for Official Launch)", use_container_width=True):
                run_query("DELETE FROM transactions")
                st.success("All history cleared!")
                st.rerun()

    # Added 'id as "Log ID"' to the SQL query so the admin knows which number to type
    df_history = get_data('''SELECT 
                             id as "Log ID",
                             SPLIT_PART(timestamp, ' ', 1) as "Date",
                             SPLIT_PART(timestamp, ' ', 2) as "Time (IST)",
                             user_name as "User", 
                             category as "Type", item_code as "Code", item_name as "Component", 
                             specs as "Specifications", action as "IN/OUT", 
                             quantity as "Qty", project as "Project" 
                             FROM transactions ORDER BY id DESC''')
    
    st.dataframe(df_history, use_container_width=True, hide_index=True)
