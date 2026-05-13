import streamlit as st
from st_supabase_connection import SupabaseConnection
import urllib.parse
from datetime import datetime

# --- CONFIG ---
st.set_page_config(page_title="Kaveri Guest Manager", layout="centered", initial_sidebar_state="collapsed")

# Initialize Supabase Connection
conn = st.connection("supabase", type=SupabaseConnection)

# --- PERFORMANCE OPTIMIZATION: DATE FILTER ---
today_start = f"{datetime.now().strftime('%Y-%m-%d')}T00:00:00"

# --- PERSISTENT LOGIN (SURVIVES PAGE REFRESH) ---
if "manager_logged_in" not in st.session_state:
    # Check if the URL has our secret login token
    if st.query_params.get("logged_in") == "true":
        st.session_state.manager_logged_in = True
    else:
        st.session_state.manager_logged_in = False

# --- UI: ROLE SELECTOR ---
st.title("🏛️ Kaveri GM")
# Changed "Staff" to "Team"
role = st.segmented_control("Select Role", ["On-Ground Team 🏃", "Manager 👔"], default="On-Ground Team 🏃")
st.divider()

# ==========================================
#              MANAGER UI
# ==========================================
if role == "Manager 👔":
    
    if not st.session_state.manager_logged_in:
        st.subheader("🔒 Manager Access")
        pwd_input = st.text_input("Enter Admin Password", type="password")
        correct_password = st.secrets.get("MANAGER_PASSWORD", "kaveri_admin") 
        
        if st.button("Login", type="primary"):
            if pwd_input == correct_password:
                st.session_state.manager_logged_in = True
                # Set URL param so they survive page refreshes!
                st.query_params["logged_in"] = "true"
                st.rerun() 
            else:
                st.error("Incorrect password.")
                
    else:
        col_space, col_logout = st.columns([4, 1])
        if col_logout.button("Logout"):
            st.session_state.manager_logged_in = False
            # Remove URL param
            if "logged_in" in st.query_params:
                del st.query_params["logged_in"]
            st.rerun()
            
        # --- 1. EXPECTED GUESTS CHECK-IN ---
        st.subheader("📥 Incoming Guests")
        st.caption("Tap a lounge button to instantly check a guest in.")
        
        res = conn.table("guests").select("*").eq("is_active", False).eq("has_left_kaveri", False).gte("created_at", today_start).execute()
        expected_guests = res.data

        if not expected_guests:
            st.info("No new expected guests at the moment.")
        else:
            for guest in expected_guests:
                with st.expander(f"👤 {guest['guest_name']} ({guest['session_type']})"):
                    st.write("Assign Lounge:")
                    
                    # High-Speed Manager Buttons (replaces dropdown)
                    btn_cols = st.columns(5)
                    lounges = ["L1", "L2", "L3", "BR", "L5"]
                    
                    for i, l_name in enumerate(lounges):
                        if btn_cols[i].button(l_name, key=f"mgr_{l_name}_{guest['id']}", use_container_width=True):
                            # Instantly update and make active in one tap
                            conn.table("guests").update({
                                "is_active": True,
                                "lounge": l_name
                            }).eq("id", guest['id']).execute()
                            st.toast(f"{guest['guest_name']} sent to {l_name}!")
                            st.rerun()

        st.write("---") 

        # --- 2. CURRENTLY ACTIVE GUESTS ---
        st.subheader("🟢 Currently Active Guests")
        st.caption("Overview of guests currently inside the building.")
        
        # Only fetch people who haven't met Gurudev yet for the active queue
        res_active = conn.table("guests").select("*").eq("is_active", True).eq("met_gurudev", False).gte("created_at", today_start).execute()
        mgr_active_guests = res_active.data
        
        if not mgr_active_guests:
            st.info("No guests are currently active inside the building.")
        else:
            for ag in mgr_active_guests:
                st.markdown(f"**{ag['guest_name']}** | Lounge: **{ag['lounge']}**")

        st.write("---") 

        # --- 3. ADD GUESTS FEATURE ---
        with st.expander("➕ Add New Expected Guests", expanded=False):
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
#           ON-GROUND TEAM UI
# ==========================================
elif role == "On-Ground Team 🏃":
    st.subheader("📍 Active Guests")

    # --- REALTIME AUTO-REFRESH ENGINE ---
    # This magically refreshes the data inside this function every 10s without making the screen flicker
    @st.fragment(run_every="10s")
    def team_dashboard():
        # Only fetch active guests who have NOT met Gurudev yet
        res = conn.table("guests").select("*").eq("is_active", True).eq("met_gurudev", False).gte("created_at", today_start).execute()
        active_guests = res.data

        if not active_guests:
            st.success("No active guests currently waiting. Take a breather! ☕")
            return

        # Create a dictionary to power the search box
        guest_dict = {g['guest_name']: g for g in active_guests}
        
        # Search Box with Auto-complete
        selected_name = st.selectbox(
            "🔍 Search / Select a Guest:", 
            options=list(guest_dict.keys()), 
            index=None, 
            placeholder="Type a name to begin..."
        )

        # Only display the card if a guest is selected
        if selected_name:
            guest = guest_dict[selected_name]
            
            with st.container(border=True):
                st.markdown(f"### 👤 {guest['guest_name']}")
                
                # --- AUTO-SAVING LOUNGE CHANGE ---
                lounge_options = ["L1", "L2", "L3", "BR", "L5"]
                current_lounge = guest.get('lounge', 'L1')
                if current_lounge not in lounge_options:
                    lounge_options.insert(0, current_lounge)
                    
                new_lounge = st.selectbox("Current Lounge:", options=lounge_options, index=lounge_options.index(current_lounge), key=f"staff_l_{guest['id']}")
                if new_lounge != current_lounge:
                    conn.table("guests").update({"lounge": new_lounge}).eq("id", guest['id']).execute()
                    st.rerun()

                st.divider()

                # --- AUTO-SAVING TOGGLES ---
                # Video
                vid_val = guest.get('video_watched', False)
                new_vid = st.toggle("📺 LMW Video", value=vid_val, key=f"vid_{guest['id']}")
                if new_vid != vid_val:
                    conn.table("guests").update({"video_watched": new_vid}).eq("id", guest['id']).execute()
                    st.rerun()

                # Demo
                demo_val = guest.get('ip_demo_done', False)
                new_demo = st.toggle("💻 IP Demo", value=demo_val, key=f"ip_{guest['id']}")
                if new_demo != demo_val:
                    conn.table("guests").update({"ip_demo_done": new_demo}).eq("id", guest['id']).execute()
                    st.rerun()

                # Ready for Gurudev
                ready_val = True if guest.get('met_gurudev', False) else guest.get('ready_to_meet_gurudev', False)
                new_ready = st.toggle("⏳ Ready for Gurudev", value=ready_val, key=f"ready_{guest['id']}")
                if new_ready != ready_val:
                    conn.table("guests").update({"ready_to_meet_gurudev": new_ready}).eq("id", guest['id']).execute()
                    st.rerun()

                # Met Gurudev (Triggers disappearance)
                guru_val = guest.get('met_gurudev', False)
                new_guru = st.toggle("🙏 Met Gurudev", value=guru_val, key=f"guru_{guest['id']}")
                if new_guru != guru_val:
                    update_data = {"met_gurudev": new_guru}
                    if new_guru:
                        update_data["ready_to_meet_gurudev"] = True # Auto-set ready if met
                    
                    conn.table("guests").update(update_data).eq("id", guest['id']).execute()
                    if new_guru:
                        st.toast("Guest met Gurudev! Removing from list...")
                    st.rerun()
                
                st.write("") # Spacer

                # --- WHATSAPP MESSAGE ---
                # Formatted exactly as requested
                msg = (
                    f"*{new_lounge}*\n"
                    f"{guest['guest_name']}\n"
                    f"📺 Video: {'✅' if new_vid else '❌'}\n"
                    f"💻 Demo: {'✅' if new_demo else '❌'}\n"
                    f"⏳ Ready for Gurudev: {'✅' if new_ready else '❌'}\n"
                    f"🙏 Met Gurudev: {'✅' if new_guru else '❌'}"
                )
                wa_url = f"https://wa.me/?text={urllib.parse.quote(msg)}"
                st.link_button("📲 Send WhatsApp Update", wa_url, use_container_width=True)

    # Call the fragment function so it renders on the screen
    team_dashboard()
