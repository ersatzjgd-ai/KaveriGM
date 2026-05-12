import streamlit as st
from st_supabase_connection import SupabaseConnection
import urllib.parse

# --- CONFIG ---
st.set_page_config(page_title="Kaveri Guest Manager", layout="centered", initial_sidebar_state="collapsed")

# Initialize Supabase Connection
conn = st.connection("supabase", type=SupabaseConnection)

# --- STATE INITIALIZATION ---
# This remembers if the manager is logged in
if "manager_logged_in" not in st.session_state:
    st.session_state.manager_logged_in = False

# --- UI: ROLE SELECTOR ---
st.title("🏛️ Kaveri Command")
role = st.segmented_control("Select Role", ["On-Ground Staff 🏃", "Manager 👔"], default="On-Ground Staff 🏃")
st.divider()

# ==========================================
#              MANAGER UI
# ==========================================
if role == "Manager 👔":
    
    # --- PASSWORD PROTECTION ---
    if not st.session_state.manager_logged_in:
        st.subheader("🔒 Manager Access")
        pwd_input = st.text_input("Enter Admin Password", type="password")
        
        correct_password = st.secrets.get("MANAGER_PASSWORD", "kaveri_admin") 
        
        if st.button("Login", type="primary"):
            if pwd_input == correct_password:
                st.session_state.manager_logged_in = True
                st.rerun() 
            else:
                st.error("Incorrect password.")
                
    # --- ACTUAL MANAGER DASHBOARD ---
    else:
        col_space, col_logout = st.columns([4, 1])
        if col_logout.button("Logout"):
            st.session_state.manager_logged_in = False
            st.rerun()
            
        # --- 1. EXPECTED GUESTS CHECK-IN ---
        st.subheader("📥 Incoming Guests")
        st.caption("Check-in expected guests and assign lounges.")
        
        res = conn.table("guests").select("*").eq("is_active", False).eq("has_left_kaveri", False).execute()
        expected_guests = res.data

        if not expected_guests:
            st.info("No new expected guests at the moment.")
        else:
            for guest in expected_guests:
                with st.expander(f"👤 {guest['guest_name']} ({guest['session_type']})"):
                    lounge_choice = st.selectbox("Assign Lounge", ["L1", "L2", "L3", "BR", "L5"], key=f"mgr_l_{guest['id']}")
                    
                    if st.button("Mark as ACTIVE ✅", key=f"mgr_btn_{guest['id']}", type="primary", use_container_width=True):
                        conn.table("guests").update({
                            "is_active": True,
                            "lounge": lounge_choice
                        }).eq("id", guest['id']).execute()
                        st.toast(f"{guest['guest_name']} is now Active in {lounge_choice}!")
                        st.rerun()

        st.write("---") 

        # --- 2. CURRENTLY ACTIVE GUESTS ---
        st.subheader("🟢 Currently Active Guests")
        st.caption("Overview of guests currently inside the building.")
        
        res_active = conn.table("guests").select("*").eq("is_active", True).eq("has_left_kaveri", False).execute()
        mgr_active_guests = res_active.data
        
        if not mgr_active_guests:
            st.info("No guests are currently active inside the building.")
        else:
            for ag in mgr_active_guests:
                st.markdown(f"**{ag['guest_name']}** | Lounge: **{ag['lounge']}**")

        st.write("---") 

        # --- 3. ADD GUESTS FEATURE ---
        with st.expander("➕ Add New Expected Guests", expanded=False):
            st.caption("Type or paste guest names below. Put each name on a new line.")
            with st.form("add_guests_form", clear_on_submit=True):
                session_type = st.radio("Session", ["Morning", "Evening"], horizontal=True)
                guest_names_input = st.text_area("Guest Names (One per line)")
                submit_btn = st.form_submit_button("💾 Save to Database", type="primary", use_container_width=True)
                
                if submit_btn:
                    if guest_names_input.strip():
                        names_list = [name.strip() for name in guest_names_input.split('\n') if name.strip()]
                        insert_data = [{"guest_name": name, "session_type": session_type} for name in names_list]
                        conn.table("guests").insert(insert_data).execute()
                        st.success(f"Added {len(names_list)} guests!")
                        st.rerun() 
                    else:
                        st.error("Please enter at least one guest name.")


# ==========================================
#           ON-GROUND STAFF UI
# ==========================================
elif role == "On-Ground Staff 🏃":
    st.subheader("📍 Active Guests")
    
    res = conn.table("guests").select("*").eq("is_active", True).eq("has_left_kaveri", False).execute()
    active_guests = res.data

    if not active_guests:
        st.success("No active guests currently in the building! Take a breather. ☕")
    else:
        # Loop through every active guest and create a card for them
        for guest in active_guests:
            with st.container(border=True):
                
                # Title and Bold Lounge ID
                st.markdown(f"### 👤 {guest['guest_name']}")
                st.markdown(f"📍 Current Lounge: **{guest['lounge']}**")
                
                # Lounge Re-Assignment Dropdown
                lounge_options = ["L1", "L2", "L3", "BR", "L5"]
                current_lounge = guest.get('lounge', 'L1')
                if current_lounge not in lounge_options:
                    lounge_options.insert(0, current_lounge)
                    
                new_lounge = st.selectbox(
                    "Change Lounge?", 
                    options=lounge_options, 
                    index=lounge_options.index(current_lounge), 
                    key=f"staff_l_{guest['id']}"
                )
                
                # Toggles (With unique keys mapped to their database ID)
                c1, c2 = st.columns(2)
                video = c1.toggle("📺 LMW Video", value=guest.get('video_watched', False), key=f"vid_{guest['id']}")
                ip_demo = c2.toggle("💻 IP Demo", value=guest.get('ip_demo_done', False), key=f"ip_{guest['id']}")
                
                c3, c4 = st.columns(2)
                # If they already met Gurudev in the DB, they are inherently "Ready". Otherwise fetch standard ready status.
                initial_ready_status = True if guest.get('met_gurudev', False) else guest.get('ready_to_meet_gurudev', False)
                ready_gurudev = c3.toggle("⏳ Ready for Gurudev", value=initial_ready_status, key=f"ready_{guest['id']}")
                gurudev = c4.toggle("🙏 Met Gurudev", value=guest.get('met_gurudev', False), key=f"guru_{guest['id']}")
                
                # Overriding the 'Ready' value if 'Met Gurudev' is flipped to True in this current session
                if gurudev:
                    ready_gurudev = True
                
                c5, c6 = st.columns(2)
                gift = c5.toggle("🎁 Gift Given", value=guest.get('gift_given', False), key=f"gift_{guest['id']}")
                
                st.divider()
                
                left_building = st.toggle("🚪 Guest Left Kaveri (Checkout)", value=False, key=f"left_{guest['id']}")

                # Prepare WhatsApp Message dynamically with updated emojis and wording
                status_emoji = "✅ Departed" if left_building else "📍 Still at Kaveri"
                msg = (
                    f"*Status Update: {guest['guest_name']}*\n"
                    f"Lounge: {new_lounge}\n"
                    f"📺 Video: {'✅' if video else '❌'}\n"
                    f"💻 Demo: {'✅' if ip_demo else '❌'}\n"
                    f"⏳ Ready for Gurudev: {'✅' if ready_gurudev else '❌'}\n"
                    f"🙏 Met Gurudev: {'✅' if gurudev else '❌'}\n"
                    f"🎁 Gift: {'✅' if gift else '❌'}\n"
                    f"Status: {status_emoji}"
                )
                wa_url = f"https://wa.me/?text={urllib.parse.quote(msg)}"

                # Side-by-Side Action Buttons for Mobile speed
                btn_col1, btn_col2 = st.columns(2)
                
                if btn_col1.button("💾 Save Status", type="primary", use_container_width=True, key=f"save_{guest['id']}"):
                    conn.table("guests").update({
                        "lounge": new_lounge,
                        "video_watched": video,
                        "ip_demo_done": ip_demo,
                        "ready_to_meet_gurudev": ready_gurudev,
                        "met_gurudev": gurudev,
                        "gift_given": gift,
                        "has_left_kaveri": left_building,
                        "is_active": not left_building 
                    }).eq("id", guest['id']).execute()

                    st.toast(f"Updated {guest['guest_name']}!")
                    st.rerun() 

                btn_col2.link_button("📲 WhatsApp", wa_url, use_container_width=True)
