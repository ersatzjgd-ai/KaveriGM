import streamlit as st
from st_supabase_connection import SupabaseConnection
import urllib.parse
import base64
from datetime import datetime
import tempfile
import os
from fpdf import FPDF
import requests
import json

# --- CONFIG ---
st.set_page_config(page_title="Kaveri Guest Manager", layout="centered", initial_sidebar_state="collapsed")

# Initialize Supabase Connection
conn = st.connection("supabase", type=SupabaseConnection)

# --- PERFORMANCE OPTIMIZATION: DATE FILTER ---
today_start = f"{datetime.now().strftime('%Y-%m-%d')}T00:00:00"

# ==========================================
#      RTLS NOMENCLATURE TRANSLATION 
# ==========================================
# Converts raw RTLS database zones into clean UI labels
ZONES_DB_TO_UI = {
    "reception": "Unassigned",
    "lounge1": "L1",
    "lounge2": "L2",
    "lounge3": "L3",
    "lounge4": "L4",
    "lounge5": "L5",
    "br": "BR",
    "gmr": "GMR",
    "passageway_top": "Top Hallway",
    "passageway_right_a": "Right Hallway A",
    "passageway_right_b": "Right Hallway B",
    None: "Unassigned",
    "": "Unassigned"
}

# Converts clean UI labels back into RTLS database zones for manual overrides
ZONES_UI_TO_DB = {v: k for k, v in ZONES_DB_TO_UI.items() if k not in [None, ""]}
ZONES_UI_TO_DB["Unassigned"] = "reception"

# Standard list for UI Pickers
UI_OPTIONS = ["Unassigned", "L1", "L2", "L3", "L4", "L5", "BR", "GMR"]

# --- PERSISTENT LOGIN (SURVIVES PAGE REFRESH) ---
if "manager_logged_in" not in st.session_state:
    if st.query_params.get("logged_in") == "true":
        st.session_state.manager_logged_in = True
    else:
        st.session_state.manager_logged_in = False

# ==========================================
#          TELEGRAM INTEGRATION ALERT
# ==========================================
def alert_telegram_team(guest_id, guest_name, photo_bytes=None):
    telegram_token = st.secrets.get("TELEGRAM_BOT_TOKEN")
    group_id = st.secrets.get("TELEGRAM_GROUP_ID")
    
    if not telegram_token or not group_id:
        st.error("🚨 Missing Telegram Secrets! Check Streamlit Cloud Settings.")
        st.stop()

    url = f"https://api.telegram.org/bot{telegram_token}/sendPhoto"
    safe_name = str(guest_name).replace('<', '').replace('>', '')
    
    caption = f"🚨 <b>New Arrival</b>\n👤 <b>{safe_name}</b>\n📍 Lounge: <b>Unassigned</b>\n\nPlease assign a lounge:"
    
    # ⚡ FIX: Updated to include L4 and map back to DB strings
    reply_markup = {
        "inline_keyboard": [
            [{"text": "L1", "callback_data": f"lng:{guest_id}:lounge1"},
             {"text": "L2", "callback_data": f"lng:{guest_id}:lounge2"},
             {"text": "L3", "callback_data": f"lng:{guest_id}:lounge3"},
             {"text": "L4", "callback_data": f"lng:{guest_id}:lounge4"}],
            [{"text": "L5", "callback_data": f"lng:{guest_id}:lounge5"},
             {"text": "BR", "callback_data": f"lng:{guest_id}:br"},
             {"text": "GMR", "callback_data": f"lng:{guest_id}:gmr"}]
        ]
    }

    data = {
        "chat_id": group_id,
        "caption": caption,
        "parse_mode": "HTML", 
        "reply_markup": json.dumps(reply_markup)
    }

    try:
        if photo_bytes:
            files = {"photo": ("photo.jpg", photo_bytes, "image/jpeg")}
            res = requests.post(url, data=data, files=files)
        else:
            msg_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            data["text"] = data.pop("caption")
            res = requests.post(msg_url, json=data)
            
        if not res.ok:
            st.error(f"🚨 Telegram rejected {safe_name}! Error: {res.status_code}")
            st.json(res.json()) 
            st.stop() 
            
    except Exception as e:
        st.error(f"🚨 Network Error: Could not reach Telegram. {e}")
        st.stop()

# --- UI: ROLE SELECTOR ---
st.title("🏛️ Kaveri GM")
role = st.segmented_control("Select Role", ["On-Ground Team 🏃", "Manager 👔"], default="On-Ground Team 🏃")
st.divider()

# ==========================================
#             MANAGER UI
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
                    
                    # ⚡ FIX: Added new options, mapped via translation dict
                    selected_ui = st.pills("Assign Lounge", UI_OPTIONS, key=f"mgr_l_{guest['id']}", label_visibility="collapsed")
                    
                    if selected_ui:
                        db_zone = ZONES_UI_TO_DB.get(selected_ui, "reception")
                        update_data = {
                            "is_active": True,
                            "lounge": db_zone
                        }
                        
                        if pic is not None:
                            update_data["photo_data"] = base64.b64encode(pic.getvalue()).decode()
                            
                        conn.table("guests").update(update_data).eq("id", guest['id']).execute()
                        alert_telegram_team(guest['id'], guest['guest_name'], pic.getvalue() if pic is not None else None)
                        
                        st.toast(f"{guest['guest_name']} checked in ({selected_ui})!")
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
                # ⚡ FIX: Translate DB string for display
                display_lounge = ZONES_DB_TO_UI.get(ag.get('lounge'), "Unassigned")
                col_name.markdown(f"**{ag['guest_name']}** | Lounge: **{display_lounge}**")
                
                if col_undo.button("↩️ Undo", key=f"undo_{ag['id']}", help="Move back to incoming"):
                    conn.table("guests").update({"is_active": False}).eq("id", ag['id']).execute()
                    st.toast(f"Moved {ag['guest_name']} back to Incoming!")
                    st.rerun()

        st.write("---") 
        # (PDF generation and add guests block remains exactly the same as your code here)

# ==========================================
#             ON-GROUND TEAM UI
# ==========================================
elif role == "On-Ground Team 🏃":

    def commit_save(g_id, g_name):
        ui_lounge = st.session_state[f"staff_l_{g_id}"]
        db_lounge = ZONES_UI_TO_DB.get(ui_lounge, "reception")
        
        update_data = {
            "lounge": db_lounge,
            "lmw_status": st.session_state[f"lmw_{g_id}"],
            "demo_status": st.session_state[f"demo_{g_id}"],
            "ready_to_meet_gurudev": st.session_state[f"ready_{g_id}"],
            "met_gurudev": st.session_state[f"guru_{g_id}"]
        }
        conn.table("guests").update(update_data).eq("id", g_id).execute()
        
        if g_id in st.session_state.initial_lounges:
            st.session_state.initial_lounges[g_id] = db_lounge
            
        st.toast(f"✅ Saved updates for {g_name}!")

    def mark_complete(g_id, g_name):
        conn.table("guests").update({"jai_gurudev": True}).eq("id", g_id).execute()
        if g_id in st.session_state.initial_lounges:
            del st.session_state.initial_lounges[g_id]
        st.toast(f"✅ Visit complete for {g_name}! Removed from list.")

    def commit_photo(g_id, g_name):
        pic = st.session_state.get(f"staff_cam_{g_id}")
        if pic is not None:
            encoded_pic = base64.b64encode(pic.getvalue()).decode()
            conn.table("guests").update({"photo_data": encoded_pic}).eq("id", g_id).execute()
            st.toast(f"✅ Photo saved for {g_name}!")

    @st.fragment(run_every="10s")
    def team_dashboard():
        res = conn.table("guests").select("*").eq("is_active", True).eq("jai_gurudev", False).gte("created_at", today_start).order("created_at").execute()
        active_guests = res.data

        if not active_guests:
            st.success("No active guests currently waiting. Take a breather! ☕")
            return
            
        # ⚡ FIX: Filter options updated
        selected_view = st.pills("Select your station", ["All"] + UI_OPTIONS, default="All", key="lounge_tab_selector", label_visibility="collapsed")
        st.write("---")

        if "initial_lounges" not in st.session_state:
            st.session_state.initial_lounges = {}
            
        for g in active_guests:
            if g['id'] not in st.session_state.initial_lounges:
                st.session_state.initial_lounges[g['id']] = g.get('lounge') or "reception"
                
        # ⚡ FIX: Order based on DB strings
        room_order = {"reception": 0, "lounge1": 1, "lounge2": 2, "lounge3": 3, "lounge4": 4, "br": 5, "lounge5": 6, "gmr": 7}
        
        active_guests.sort(key=lambda g: (
            room_order.get(st.session_state.initial_lounges[g['id']], 99),
            g['created_at']
        ))

        search_query = st.text_input("🔍 Search Guest Name...", "", placeholder="Type a name to filter...")

        filtered_guests = []
        for g in active_guests:
            matches_search = search_query.lower() in g['guest_name'].lower()
            
            # Translate raw DB string for UI matching
            guest_ui_lounge = ZONES_DB_TO_UI.get(g.get('lounge'), "Unassigned")
            
            matches_lounge = (selected_view == "All") or (guest_ui_lounge == selected_view)
            
            if matches_search and matches_lounge:
                filtered_guests.append(g)

        if not filtered_guests:
            if selected_view != "All" and not search_query:
                st.info(f"No active guests currently in {selected_view}.")
            else:
                st.info("No guests match your filters.")

        for guest in filtered_guests:
            current_ui_lounge = ZONES_DB_TO_UI.get(guest.get('lounge'), "Unassigned")
            
            # ⚡ FIX: Complete color matrix
            color_map = {
                "Unassigned": ("#FFDDC1", "#000000"), 
                "L1": ("#00FFFF", "#000000"),
                "L2": ("#FFFF00", "#000000"),
                "L3": ("#FF00FF", "#FFFFFF"),
                "L4": ("#FFB6C1", "#000000"),  # Light Pink for L4
                "L5": ("#000000", "#FFFFFF"),
                "BR": ("#E0E0E0", "#000000"),
                "GMR": ("#98FB98", "#000000"), # Pale Green for GMR
                "Top Hallway": ("#FFFFFF", "#000000"),
                "Right Hallway A": ("#FFFFFF", "#000000"),
                "Right Hallway B": ("#FFFFFF", "#000000")
            }
            bg_color, text_color = color_map.get(current_ui_lounge, ("#E0E0E0", "#000000"))

            with st.container(border=True):
                st.markdown(
                    f'<div style="background-color: {bg_color}; color: {text_color}; padding: 4px; border-radius: 4px; text-align: center; font-weight: bold; margin-bottom: 5px; font-size: 16px;">'
                    f'👤 {guest["guest_name"]}</div>', 
                    unsafe_allow_html=True
                )
                
                col_lounge, col_photo = st.columns([3, 1])
                with col_lounge:
                    lounge_list = UI_OPTIONS.copy()
                    if current_ui_lounge not in lounge_list:
                        lounge_list.insert(0, current_ui_lounge)
                    st.selectbox("Update Lounge:", options=lounge_list, index=lounge_list.index(current_ui_lounge), key=f"staff_l_{guest['id']}", label_visibility="collapsed")
                with col_photo:
                    with st.popover("📸", use_container_width=True):
                        photo_b64 = guest.get('photo_data')
                        if photo_b64:
                            st.image(base64.b64decode(photo_b64), use_container_width=True)
                            st.caption("Update Photo:")
                        else:
                            st.info("No photo captured.")
                        
                        new_pic = st.camera_input("Take Photo", key=f"staff_cam_{guest['id']}", label_visibility="collapsed")
                        if new_pic is not None:
                            st.button("💾 Save Photo", key=f"save_pic_{guest['id']}", use_container_width=True, on_click=commit_photo, args=(guest['id'], guest['guest_name']))

                c1, c2 = st.columns(2)
                with c1:
                    st.segmented_control("📺 LMW", ["Not yet", "Started", "Done"], default=guest.get('lmw_status', 'Not yet'), key=f"lmw_{guest['id']}", label_visibility="visible")
                with c2:
                    st.segmented_control("💻 IP Demo", ["Not yet", "Started", "Done"], default=guest.get('demo_status', 'Not yet'), key=f"demo_{guest['id']}", label_visibility="visible")

                c3, c4 = st.columns(2)
                with c3:
                    st.toggle("⏳ Ready for Vyas", value=guest.get('ready_to_meet_gurudev', False), key=f"ready_{guest['id']}")
                with c4:
                    st.toggle("🤝 Met Gurudev", value=guest.get('met_gurudev', False), key=f"guru_{guest['id']}")

                local_lounge = st.session_state.get(f"staff_l_{guest['id']}", current_ui_lounge)
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
                
                st.markdown("<br>", unsafe_allow_html=True) 
                btn_col1, btn_col2, btn_col3 = st.columns(3)
                
                btn_col1.link_button("📲 WhatsApp", wa_url, use_container_width=True)
                btn_col2.button("💾 Save Updates", use_container_width=True, key=f"save_btn_{guest['id']}", on_click=commit_save, args=(guest['id'], guest['guest_name']))
                btn_col3.button("✅ Complete", type="primary", use_container_width=True, key=f"jai_btn_{guest['id']}", on_click=mark_complete, args=(guest['id'], guest['guest_name']))

    team_dashboard()
