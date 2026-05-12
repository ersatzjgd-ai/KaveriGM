import streamlit as st
from st_supabase_connection import SupabaseConnection
import urllib.parse
import random
import string

# --- CONFIG ---
st.set_page_config(page_title="Kaveri Guest Manager", layout="centered", initial_sidebar_state="collapsed")

# Initialize Supabase Connection
# (Relies on Streamlit Secrets for SUPABASE_URL and SUPABASE_KEY)
conn = st.connection("supabase", type=SupabaseConnection)

# --- HELPER FUNCTIONS ---
def generate_password(length=6):
    """Generates a quick, readable password for guests."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# --- UI: ROLE SELECTOR ---
st.title("🏛️ Kaveri Command")
# A fast toggle switch at the top of the app
role = st.segmented_control("Select Role", ["On-Ground Staff 🏃", "Manager 👔"], default="On-Ground Staff 🏃")
st.divider()

# ==========================================
#              MANAGER UI
# ==========================================
if role == "Manager 👔":
    
    # --- 1. EXPECTED GUESTS CHECK-IN (TOP PRIORITY) ---
    st.subheader("📥 Incoming Guests")
    st.caption("Check-in expected guests, assign lounges, and generate access.")
    
    # Fetch guests who haven't left and aren't active yet (Expected guests)
    res = conn.table("guests").select("*").eq("is_active", False).eq("has_left_kaveri", False).execute()
    expected_guests = res.data

    if not expected_guests:
        st.info("No new expected guests at the moment.")
    else:
        for guest in expected_guests:
            # Use an expander to keep the list clean and compact on mobile
            with st.expander(f"👤 {guest['guest_name']} ({guest['session_type']})"):
                
                # Manager Actions
                lounge_choice = st.selectbox("Assign Lounge", ["L1", "L2", "L3", "BR", "L5"], key=f"mgr_l_{guest['id']}")
                
                col1, col2 = st.columns([3, 1])
                new_pass = col1.text_input("Access Password", value=generate_password(), key=f"mgr_p_{guest['id']}")
                
                if st.button("Mark as ACTIVE ✅", key=f"mgr_btn_{guest['id']}", type="primary", use_container_width=True):
                    # Update DB to make them active for the ground staff
                    conn.table("guests").update({
                        "is_active": True,
                        "lounge": lounge_choice,
                        "access_password": new_pass
                    }).eq("id", guest['id']).execute()
                    
                    st.toast(f"{guest['guest_name']} is now Active in {lounge_choice}!")
                    st.rerun()

    st.write("---") # Visual separator

    # --- 2. ADD GUESTS FEATURE ---
    with st.expander("➕ Add New Expected Guests", expanded=False):
        st.caption("Type or paste guest names below. Put each name on a new line.")
        
        with st.form("add_guests_form", clear_on_submit=True):
            session_type = st.radio("Session", ["Morning", "Evening"], horizontal=True)
            guest_names_input = st.text_area("Guest Names (One per line)")
            
            submit_btn = st.form_submit_button("💾 Save to Database", type="primary", use_container_width=True)
            
            if submit_btn:
                if guest_names_input.strip():
                    # Split by line and remove empty spaces
                    names_list = [name.strip() for name in guest_names_input.split('\n') if name.strip()]
                    
                    # Prepare data for Supabase batch insert
                    insert_data = [
                        {"guest_name": name, "session_type": session_type} 
                        for name in names_list
                    ]
                    
                    # Execute Insert
                    conn.table("guests").insert(insert_data).execute()
                    
                    st.success(f"Added {len(names_list)} guests to the {session_type} session!")
                    st.rerun() # Refresh the page to show the new guests in the Incoming list
                else:
                    st.error("Please enter at least one guest name.")

# ==========================================
#           ON-GROUND STAFF UI
# ==========================================
elif role == "On-Ground Staff 🏃":
    st.subheader("📍 Active Guests")
    
    # Fetch ONLY guests who are currently Active in the building
    res = conn.table("guests").select("*").eq("is_active", True).eq("has_left_kaveri", False).execute()
    active_guests = res.data

    if not active_guests:
        st
