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
    if st.query_params.get("logged_in") == "true":
        st.session_state.manager_logged_in = True
    else:
        st.session_state.manager_logged_in = False

# --- UI: ROLE SELECTOR ---
st.title("🏛️ Kaveri Command")
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
                st.query_params["logged_in"] = "true"
                st.rerun() 
            else:
                st.error("Incorrect password.")
                
    else:
        col_space, col_logout = st.columns([4, 1])
        if col_logout.button("Logout"):
            st.session_state.manager_logged_in = False
            if "logged_in" in st.query_params:
                del st.query_params["logged_in"]
            st.rerun()
            
        # --- 1. ULTRA-COMPACT EXPECTED GUESTS CHECK-IN ---
        st.subheader("📥 Incoming Guests")
        st.caption("Tap a lounge button to instantly check a guest in.")
        
        res = conn.table("guests").select("*").eq("is_active", False).eq("has_left_kaveri", False).gte("created_at", today_start).execute()
        expected_guests = res.data

        if not expected_guests:
            st.info("No new expected guests at the moment.")
        else:
            for guest in expected_guests:
                # Removed the expander to make it ultra-compact and fast
                with st.container(border=True):
                    st.markdown(f"**👤 {guest['guest_name']}** ({guest['session_type']})")
                    
                    btn_cols = st.columns(5)
                    lounges = ["L1", "L2", "L3", "BR", "L5"]
                    
                    for i, l_name in enumerate(lounges):
                        if btn_cols[i].button(l_name, key=f"mgr_{l_name}_{guest['id']}", use_container_width=True):
                            conn.table("guests").update({
                                "is_active": True,
                                "lounge": l_name
                            }).eq("id", guest['id']).execute()
                            st.toast(f"{guest['guest_name']} sent to {l_name}!")
                            st.rerun()

        st.write("---") 

        # --- 2. CURRENTLY ACTIVE GUESTS ---
        st.subheader("🟢 Currently Active Guests")
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
    @st.fragment(run_every="10s")
    def team_dashboard():
        res = conn.table("guests").select("*").eq("is_active", True).eq("met_gurudev", False).gte("created_at", today_start).execute()
        active_guests = res.data

        if not active_guests:
            st.success("No active guests currently waiting. Take a breather! ☕")
            return
            
        # --- THE FILTER BAR ---
        search_query = st.text_input("🔍 Search Guest Name...", "", placeholder="Type a name to filter the list below...")
        
        # Filter the list based on search (shows all if search is empty)
        filtered_guests = [g for g in active_guests if search_query.lower() in g['guest_name'].lower()]

        if not filtered_guests:
            st.info("No guests match that name.")

        for guest in filtered_guests:
            current_lounge = guest.get('lounge', 'L1')
            
            # --- CMYK COLOR CODING MAPPING ---
            color_map = {
                "L1": ("#00FFFF", "#000000"), # Cyan (Black text)
                "L2": ("#FFFF00", "#000000"), # Yellow (Black text)
                "L3": ("#FF00FF", "#FFFFFF"), # Magenta (White text)
                "L5": ("#000000", "#FFFFFF"), # Black (White text)
                "BR": ("#E0E0E0", "#000000")  # Default Gray
            }
            bg_color, text_color = color_map.get(current_lounge, ("#E0E0E0", "#000000"))

            with st.container(border=True):
                # HTML injection for the colored banner
                st.markdown(
                    f'<div style="background-color: {bg_color}; color: {text_color}; padding: 8px; border-radius: 5px; text-align: center; font-weight: bold; margin-bottom: 10px; font-size: 18px;">'
                    f'👤 {guest["guest_name"]} &nbsp;|&nbsp; {current_lounge}</div>', 
                    unsafe_allow_html=True
                )
                
                # --- AUTO-SAVING LOUNGE CHANGE ---
                lounge_options = ["L1", "L2", "L3", "BR", "L5"]
                if current_lounge not in lounge_options:
                    lounge_options.insert(0, current_lounge)
                    
                new_lounge = st.selectbox("Update Lounge:", options=lounge_options, index=lounge_options.index(current_lounge), key=f"staff_l_{guest['id']}", label_visibility="collapsed")
                if new_lounge != current_lounge:
                    conn.table("guests").update({"lounge": new_lounge}).eq("id", guest['id']).execute()
                    st.rerun()

                # --- ULTRA-COMPACT 2x2 TOGGLE GRID ---
                c1, c2 = st.columns(2)
                
                # Video (Row 1, Col 1)
                vid_val = guest.get('video_watched', False)
                new_vid = c1.toggle("📺 Video", value=vid_val, key=f"vid_{guest['id']}")
                if new_vid != vid_val:
                    conn.table("guests").update({"video_watched": new_vid}).eq("id", guest['id']).execute()
                    st.rerun()

                # Demo (Row 1, Col 2)
                demo_val = guest.get('ip_demo_done', False)
                new_demo = c2.toggle("💻 Demo", value=demo_val, key=f"ip_{guest['id']}")
                if new_demo != demo_val:
                    conn.table("guests").update({"ip_demo_done": new_demo}).eq("id", guest['id']).execute()
                    st.rerun()

                # Ready for Gurudev (Row 2, Col 1)
                ready_val = True if guest.get('met_gurudev', False) else guest.get('ready_to_meet_gurudev', False)
                new_ready = c1.toggle("⏳ Ready", value=ready_val, key=f"ready_{guest['id']}")
                if new_ready != ready_val:
                    conn.table("guests").update({"ready_to_meet_gurudev": new_ready}).eq("id", guest['id']).execute()
                    st.rerun()

                # Met Gurudev (Row 2, Col 2 - Triggers disappearance)
                guru_val = guest.get('met_gurudev', False)
                new_guru = c2.toggle("🙏 Met Gurudev", value=guru_val, key=f"guru_{guest['id']}")
                if new_guru != guru_val:
                    update_data = {"met_gurudev": new_guru}
                    if new_guru:
                        update_data["ready_to_meet_gurudev"] = True 
                    
                    conn.table("guests").update(update_data).eq("id", guest['id']).execute()
                    if new_guru:
                        st.toast(f"{guest['guest_name']} met Gurudev! Removing from list...")
                    st.rerun()
                
                # --- WHATSAPP MESSAGE ---
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

    # Render the auto-refreshing UI
    team_dashboard()
