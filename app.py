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
        # A quick logout button at the top right
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
                    # Simplified to just the Lounge Dropdown
                    lounge_choice = st.selectbox("Assign Lounge", ["L1", "L2", "L3", "BR", "L5"], key=f"mgr_l_{guest['id']}")
                    
                    if st.button("Mark as ACTIVE ✅", key=f"mgr_btn_{guest['id']}", type="primary", use_container_width=True):
                        conn.table("guests").update({
                            "is_active": True,
                            "lounge": lounge_choice
                        }).eq("id", guest['id']).execute()
                        st.toast(f"{guest['guest_name']} is now Active in {lounge_choice}!")
                        st.rerun()

        st.write("---") 

        # --- 2. ADD GUESTS FEATURE ---
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

        st.write("---") 

        # --- 3. CURRENTLY ACTIVE GUESTS ---
        st.subheader("🟢 Currently Active Guests")
        st.caption("Overview of guests currently inside the building.")
        
        res_active = conn.table("guests").select("*").eq("is_active", True).eq("has_left_kaveri", False).execute()
        mgr_active_guests = res_active.data
        
        if not mgr_active_guests:
            st.info("No guests are currently active inside the building.")
        else:
            for ag in mgr_active_guests:
                # Removed the Wi-Fi password display here
                st.markdown(f"**{ag['guest_name']}** | Lounge: **{ag['lounge']}**")


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
        guest_dict = {f"{g['guest_name']} - {g['lounge']}": g for g in active_guests}
        
        selected_guest_label = st.selectbox("Select Guest to Update:", options=list(guest_dict.keys()))
        selected_guest = guest_dict[selected_guest_label]
        g_id = selected_guest['id']

        with st.container(border=True):
            st.markdown(f"### {selected_guest['guest_name']}")
            # Removed the Wi-Fi password display here as well
            st.caption(f"**Lounge:** {selected_guest['lounge']}")
            
            c1, c2 = st.columns(2)
            video = c1.toggle("📺 LMW Video", value=selected_guest.get('video_watched', False))
            ip_demo = c2.toggle("💻 IP Demo", value=selected_guest.get('ip_demo_done', False))
            
            c3, c4 = st.columns(2)
            gurudev = c3.toggle("🙏 Met Gurudev", value=selected_guest.get('met_gurudev', False))
            gift = c4.toggle("🎁 Gift Given", value=selected_guest.get('gift_given', False))
            
            st.divider()
            
            left_building = st.toggle("🚪 Guest Left Kaveri (Checkout)", value=False)

            if st.button("💾 Save Status & WhatsApp", type="primary", use_container_width=True):
                conn.table("guests").update({
                    "video_watched": video,
                    "ip_demo_done": ip_demo,
                    "met_gurudev": gurudev,
                    "gift_given": gift,
                    "has_left_kaveri": left_building,
                    "is_active": not left_building 
                }).eq("id", g_id).execute()

                st.toast("Database Updated!")

                status_emoji = "✅ Departed" if left_building else "📍 In Session"
                msg = (
                    f"*Status Update: {selected_guest['guest_name']}*\n"
                    f"Lounge: {selected_guest['lounge']}\n"
                    f"📺 Video: {'Yes' if video else 'No'}\n"
                    f"💻 Demo: {'Yes' if ip_demo else 'No'}\n"
                    f"🙏 Gurudev: {'Yes' if gurudev else 'No'}\n"
                    f"🎁 Gift: {'Yes' if gift else 'No'}\n"
                    f"Status: {status_emoji}"
                )
                wa_url = f"https://wa.me/?text={urllib.parse.quote(msg)}"
                
                st.link_button("📲 Share to WhatsApp", wa_url, use_container_width=True)
                
                if left_building:
                    st.rerun()
