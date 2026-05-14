import streamlit as st
from st_supabase_connection import SupabaseConnection
import urllib.parse
import base64
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
st.title("🏛️ Kaveri GM")
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
            
        # --- 1. EXPECTED GUESTS CHECK-IN ---
        st.subheader("📥 Incoming Guests")
        st.caption("Capture a photo, then tap a lounge pill to check-in.")
        
        # FIX: Added .order("created_at") to lock the list in place
        res = conn.table("guests").select("*").eq("is_active", False).eq("has_left_kaveri", False).gte("created_at", today_start).order("created_at").execute()
        expected_guests = res.data

        search_incoming = st.text_input("🔍 Search Expected Guest...", "", placeholder="Type a name to filter...")
        filtered_expected = [g for g in expected_guests if search_incoming.lower() in g['guest_name'].lower()]

        if not filtered_expected:
            if search_incoming:
                st.info("No expected guests match that name.")
            else:
                st.success("No new expected guests at the moment.")
        else:
            for guest in filtered_expected:
                with st.container(border=True):
                    st.markdown(f"**👤 {guest['guest_name']}** ({guest['session_type']})")
                    
                    with st.expander("📸 Capture Photo (Optional)", expanded=False):
                        pic = st.camera_input("Take Photo", key=f"cam_{guest['id']}", label_visibility="collapsed")
                    
                    selected_lounge = st.pills("Assign Lounge", ["L1", "L2", "L3", "BR", "L5"], key=f"mgr_l_{guest['id']}", label_visibility="collapsed")
                    
                    if selected_lounge:
                        update_data = {
                            "is_active": True,
                            "lounge": selected_lounge
                        }
                        
                        if pic is not None:
                            update_data["photo_data"] = base64.b64encode(pic.getvalue()).decode()
                            
                        conn.table("guests").update(update_data).eq("id", guest['id']).execute()
                        st.toast(f"{guest['guest_name']} sent to {selected_lounge}!")
                        st.rerun() # We keep rerun here because the guest needs to physically leave this list

        st.write("---") 

        # --- 2. ARRIVED GUESTS ---
        st.subheader("🟢 Arrived Guests")
        # FIX: Added .order("created_at") to lock the list in place
        res_active = conn.table("guests").select("*").eq("is_active", True).eq("jai_gurudev", False).gte("created_at", today_start).order("created_at").execute()
        mgr_active_guests = res_active.data
        
        if not mgr_active_guests:
            st.info("No guests are currently active inside the building.")
        else:
            for ag in mgr_active_guests:
                col_name, col_undo = st.columns([3, 1])
                col_name.markdown(f"**{ag['guest_name']}** | Lounge: **{ag['lounge']}**")
                
                if col_undo.button("↩️ Undo", key=f"undo_{ag['id']}", help="Move back to incoming"):
                    conn.table("guests").update({"is_active": False}).eq("id", ag['id']).execute()
                    st.toast(f"Moved {ag['guest_name']} back to Incoming!")
                    st.rerun() # Keep rerun here to move them off the list

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

    @st.fragment(run_every="10s")
    def team_dashboard():
        # FIX: Added .order("created_at") to permanently stop the shuffling!
        res = conn.table("guests").select("*").eq("is_active", True).eq("jai_gurudev", False).gte("created_at", today_start).order("created_at").execute()
        active_guests = res.data

        if not active_guests:
            st.success("No active guests currently waiting. Take a breather! ☕")
            return
            
        search_query = st.text_input("🔍 Search Guest Name...", "", placeholder="Type a name to filter the list below...")
        filtered_guests = [g for g in active_guests if search_query.lower() in g['guest_name'].lower()]

        if not filtered_guests:
            st.info("No guests match that name.")

        for guest in filtered_guests:
            current_lounge = guest.get('lounge', 'L1')
            
            color_map = {
                "L1": ("#00FFFF", "#000000"),
                "L2": ("#FFFF00", "#000000"),
                "L3": ("#FF00FF", "#FFFFFF"),
                "L5": ("#000000", "#FFFFFF"),
                "BR": ("#E0E0E0", "#000000") 
            }
            bg_color, text_color = color_map.get(current_lounge, ("#E0E0E0", "#000000"))

            with st.container(border=True):
                st.markdown(
                    f'<div style="background-color: {bg_color}; color: {text_color}; padding: 8px; border-radius: 5px; text-align: center; font-weight: bold; margin-bottom: 10px; font-size: 18px;">'
                    f'👤 {guest["guest_name"]} &nbsp;|&nbsp; {current_lounge}</div>', 
                    unsafe_allow_html=True
                )
                
                col_lounge, col_photo = st.columns([3, 1])
                
                with col_lounge:
                    lounge_options = ["L1", "L2", "L3", "BR", "L5"]
                    if current_lounge not in lounge_options:
                        lounge_options.insert(0, current_lounge)
                        
                    new_lounge = st.selectbox("Update Lounge:", options=lounge_options, index=lounge_options.index(current_lounge), key=f"staff_l_{guest['id']}", label_visibility="collapsed")
                    
                    # FIX: Removed st.rerun() from here to stop the glitching/bouncing
                    if new_lounge != current_lounge:
                        conn.table("guests").update({"lounge": new_lounge}).eq("id", guest['id']).execute()

                with col_photo:
                    with st.popover("📸", use_container_width=True):
                        photo_b64 = guest.get('photo_data')
                        if photo_b64:
                            st.image(base64.b64decode(photo_b64), use_container_width=True)
                        else:
                            st.info("No photo captured.")

                # --- 3-STATE SEGMENTED CONTROLS ---
                lmw_val = guest.get('lmw_status', 'Not yet')
                demo_val = guest.get('demo_status', 'Not yet')
                ready_val = guest.get('ready_to_meet_gurudev', False)
                guru_val = guest.get('met_gurudev', False)
                
                c1, c2 = st.columns(2)
                with c1:
                    st.caption("📺 LMW")
                    new_lmw = st.segmented_control("LMW", ["Not yet", "Started", "Done"], default=lmw_val, key=f"lmw_{guest['id']}", label_visibility="collapsed")
                with c2:
                    st.caption("💻 IP Demo")
                    new_demo = st.segmented_control("Demo", ["Not yet", "Started", "Done"], default=demo_val, key=f"demo_{guest['id']}", label_visibility="collapsed")

                c3, c4 = st.columns(2)
                new_ready = c3.toggle("⏳ Ready for Vyas", value=ready_val, key=f"ready_{guest['id']}")
                new_guru = c4.toggle("🤝 Met Gurudev", value=guru_val, key=f"guru_{guest['id']}")

                if new_lmw is None: new_lmw = lmw_val
                if new_demo is None: new_demo = demo_val

                # FIX: Removed st.rerun() from here entirely. This stops the app from snapping back to old data!
                if new_lmw != lmw_val or new_demo != demo_val or new_ready != ready_val or new_guru != guru_val:
                    update_data = {}
                    if new_lmw != lmw_val: update_data["lmw_status"] = new_lmw
                    if new_demo != demo_val: update_data["demo_status"] = new_demo
                    if new_ready != ready_val: update_data["ready_to_meet_gurudev"] = new_ready
                    if new_guru != guru_val: update_data["met_gurudev"] = new_guru
                            
                    conn.table("guests").update(update_data).eq("id", guest['id']).execute()
                
                # --- WHATSAPP MESSAGE ---
                msg = (
                    f"*{new_lounge}*\n"
                    f"{guest['guest_name']}\n"
                    f"📺 LMW: {new_lmw}\n"
                    f"💻 IP Demo: {new_demo}\n"
                    f"⏳ Ready for Vyas: {'✅' if new_ready else '❌'}\n"
                    f"🤝 Met Gurudev: {'✅' if new_guru else '❌'}"
                )
                wa_url = f"https://wa.me/?text={urllib.parse.quote(msg)}"
                
                # --- ACTION BUTTONS (BOTTOM ROW) ---
                st.write("") 
                btn_col1, btn_col2 = st.columns(2)
                btn_col1.link_button("📲 WhatsApp", wa_url, use_container_width=True)
                
                if btn_col2.button("✅ Visit Complete", type="primary", use_container_width=True, key=f"jai_btn_{guest['id']}"):
                    conn.table("guests").update({"jai_gurudev": True}).eq("id", guest['id']).execute()
                    st.toast(f"Visit complete for {guest['guest_name']}! Removing from active list...")
                    st.rerun() # Keep rerun here because they MUST leave the screen.

    team_dashboard()
