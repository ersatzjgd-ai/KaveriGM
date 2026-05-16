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
            
        st.subheader("📥 Incoming Guests")
        st.caption("Capture a photo, then tap a lounge pill to check-in.")
        
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
                        st.rerun()

        st.write("---") 

        st.subheader("🟢 Arrived Guests")
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
                    st.rerun()

        st.write("---") 

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
        res = conn.table("guests").select("*").eq("is_active", True).eq("jai_gurudev", False).gte("created_at", today_start).order("created_at").execute()
        active_guests = res.data

        if not active_guests:
            st.success("No active guests currently waiting. Take a breather! ☕")
            return
            
        # --- 🔒 ANTI-RESHUFFLE & CUSTOM ROOM SORTING LOGIC 🔒 ---
        if "initial_lounges" not in st.session_state:
            st.session_state.initial_lounges = {}
            
        for g in active_guests:
            if g['id'] not in st.session_state.initial_lounges:
                st.session_state.initial_lounges[g['id']] = g.get('lounge', 'L1')
                
        room_order = {"L1": 1, "L2": 2, "L3": 3, "BR": 4, "L5": 5}
        
        active_guests.sort(key=lambda g: (
            room_order.get(st.session_state.initial_lounges[g['id']], 99),
            g['created_at']
        ))
        # --------------------------------------------------------

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
                    f'👤 {guest["guest_name"]}</div>', 
                    unsafe_allow_html=True
                )
                
                col_lounge, col_photo = st.columns([3, 1])
                
                with col_lounge:
                    lounge_options = ["L1", "L2", "L3", "BR", "L5"]
                    if current_lounge not in lounge_options:
                        lounge_options.insert(0, current_lounge)
                        
                    # Auto-save removed
                    st.selectbox("Update Lounge:", options=lounge_options, index=lounge_options.index(current_lounge), key=f"staff_l_{guest['id']}", label_visibility="collapsed")

                with col_photo:
                    with st.popover("📸", use_container_width=True):
                        photo_b64 = guest.get('photo_data')
                        if photo_b64:
                            st.image(base64.b64decode(photo_b64), use_container_width=True)
                        else:
                            st.info("No photo captured.")

                # --- 3-STATE SEGMENTED CONTROLS (Auto-save removed) ---
                c1, c2 = st.columns(2)
                with c1:
                    st.caption("📺 LMW")
                    st.segmented_control("LMW", ["Not yet", "Started", "Done"], default=guest.get('lmw_status', 'Not yet'), key=f"lmw_{guest['id']}", label_visibility="collapsed")
                with c2:
                    st.caption("💻 IP Demo")
                    st.segmented_control("Demo", ["Not yet", "Started", "Done"], default=guest.get('demo_status', 'Not yet'), key=f"demo_{guest['id']}", label_visibility="collapsed")

                # --- STANDARD TOGGLES (Auto-save removed) ---
                c3, c4 = st.columns(2)
                st.toggle("⏳ Ready for Vyas", value=guest.get('ready_to_meet_gurudev', False), key=f"ready_{guest['id']}")
                st.toggle("🤝 Met Gurudev", value=guest.get('met_gurudev', False), key=f"guru_{guest['id']}")

                # --- INSTANT WHATSAPP LINK ---
                local_lounge = st.session_state.get(f"staff_l_{guest['id']}", current_lounge)
                local_lmw = st.session_state.get(f"lmw_{guest['id']}", guest.get('lmw_status', 'Not yet'))
                local_demo = st.session_state.get(f"demo_{guest['id']}", guest.get('demo_status', 'Not yet'))
                local_ready = st.session_state.get(f"ready_{guest['id']}", guest.get('ready_to_meet_gurudev', False))
                local_guru = st.session_state.get(f"guru_{guest['id']}", guest.get('met_gurudev', False))

                msg = (
                    f"*{local_lounge}*\n"
                    f"{guest['guest_name']}\n"
                    f"📺 LMW: {local_lmw}\n"
                    f"💻 IP Demo: {local_demo}\n"
                    f"⏳ Ready for Vyas: {'✅' if local_ready else '❌'}\n"
                    f"🤝 Met Gurudev: {'✅' if local_guru else '❌'}"
                )
                wa_url = f"https://wa.me/?text={urllib.parse.quote(msg)}"
                
                # --- ACTION BUTTONS ---
                st.markdown("<br>", unsafe_allow_html=True) 
                
                # Updated to 3 columns to fit the new Save button
                btn_col1, btn_col2, btn_col3 = st.columns(3)
                
                btn_col1.link_button("📲 WhatsApp", wa_url, use_container_width=True)
                
                # The New Manual Save Button
                if btn_col2.button("💾 Save Updates", use_container_width=True, key=f"save_btn_{guest['id']}"):
                    update_data = {
                        "lounge": st.session_state[f"staff_l_{guest['id']}"],
                        "lmw_status": st.session_state[f"lmw_{guest['id']}"],
                        "demo_status": st.session_state[f"demo_{guest['id']}"],
                        "ready_to_meet_gurudev": st.session_state[f"ready_{guest['id']}"],
                        "met_gurudev": st.session_state[f"guru_{guest['id']}"]
                    }
                    conn.table("guests").update(update_data).eq("id", guest['id']).execute()
                    st.toast(f"✅ Saved updates for {guest['guest_name']}!")
                    st.rerun() 
                
                if btn_col3.button("✅ Complete", type="primary", use_container_width=True, key=f"jai_btn_{guest['id']}"):
                    conn.table("guests").update({"jai_gurudev": True}).eq("id", guest['id']).execute()
                    
                    if guest['id'] in st.session_state.initial_lounges:
                        del st.session_state.initial_lounges[guest['id']]
                        
                    st.toast(f"Visit complete for {guest['guest_name']}! Removing from list...")
                    st.rerun() 

    team_dashboard()
