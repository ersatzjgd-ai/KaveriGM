import streamlit as st
from st_supabase_connection import SupabaseConnection
import urllib.parse
import base64

# --- CONFIG ---
st.set_page_config(page_title="Kaveri GM - Team", layout="centered", initial_sidebar_state="collapsed")

conn = st.connection("supabase", type=SupabaseConnection)

ZONES_DB_TO_UI = {
    "reception": "Unassigned", "lounge1": "L1", "lounge2": "L2", "lounge3": "L3",
    "lounge4": "L4", "lounge5": "L5", "br": "BR", "gmr": "GMR",
    "passageway_top": "Top Hallway", "passageway_right_a": "Right Hallway A",
    "passageway_right_b": "Right Hallway B", None: "Unassigned", "": "Unassigned"
}
ZONES_UI_TO_DB = {v: k for k, v in ZONES_DB_TO_UI.items() if k not in [None, ""]}
ZONES_UI_TO_DB["Unassigned"] = "reception"
UI_OPTIONS = ["Unassigned", "L1", "L2", "L3", "L4", "L5", "BR", "GMR"]
COLOR_MAP = {
    "Unassigned": ("#FFDDC1", "#000000"), "L1": ("#00FFFF", "#000000"),
    "L2": ("#FFFF00", "#000000"), "L3": ("#FF00FF", "#FFFFFF"),
    "L4": ("#FFB6C1", "#000000"), "L5": ("#000000", "#FFFFFF"),
    "BR": ("#E0E0E0", "#000000"), "GMR": ("#98FB98", "#000000"),
    "Top Hallway": ("#FFFFFF", "#000000"), "Right Hallway A": ("#FFFFFF", "#000000"),
    "Right Hallway B": ("#FFFFFF", "#000000")
}

st.title("🏃 On-Ground Portal")

# ==========================================
#          MODAL DIALOG FUNCTION
# ==========================================
@st.dialog("Manage Guest")
def guest_action_modal(guest):
    current_ui_lounge = ZONES_DB_TO_UI.get(guest.get('lounge'), "Unassigned")
    
    col_lounge, col_photo = st.columns([3, 1])
    with col_lounge:
        lounge_list = UI_OPTIONS.copy()
        if current_ui_lounge not in lounge_list:
            lounge_list.insert(0, current_ui_lounge)
        new_lounge = st.selectbox("Update Lounge:", options=lounge_list, index=lounge_list.index(current_ui_lounge), label_visibility="collapsed")
    
    with col_photo:
        with st.popover("📸", use_container_width=True):
            if guest.get('photo_data'):
                st.image(base64.b64decode(guest['photo_data']), use_container_width=True)
            else:
                st.info("No photo.")
            new_pic = st.camera_input("Update Photo", label_visibility="collapsed")

    c1, c2 = st.columns(2)
    with c1:
        new_lmw = st.segmented_control("📺 LMW", ["Not yet", "Started", "Done"], default=guest.get('lmw_status', 'Not yet') if guest.get('lmw_status') else 'Not yet')
    with c2:
        new_demo = st.segmented_control("💻 IP Demo", ["Not yet", "Started", "Done"], default=guest.get('demo_status', 'Not yet') if guest.get('demo_status') else 'Not yet')

    c3, c4 = st.columns(2)
    with c3:
        new_ready = st.toggle("⏳ Ready for Vyas", value=bool(guest.get('ready_to_meet_gurudev', False)))
    with c4:
        new_guru = st.toggle("🤝 Met Gurudev", value=bool(guest.get('met_gurudev', False)))

    msg = f"*{new_lounge}*\n{guest['guest_name']}\n📺 LMW: {new_lmw}\n💻 IP Demo: {new_demo}\n⏳ Ready for Vyas: {'✅' if new_ready else '❌'}\n🤝 Met Gurudev: {'✅' if new_guru else '❌'}"
    wa_url = f"https://wa.me/?text={urllib.parse.quote(msg)}"
    
    st.markdown("<br>", unsafe_allow_html=True) 
    btn_col1, btn_col2, btn_col3 = st.columns(3)
    
    btn_col1.link_button("📲 WhatsApp", wa_url, use_container_width=True)
    
    if btn_col2.button("💾 Save", use_container_width=True):
        update_data = {
            "lounge": ZONES_UI_TO_DB.get(new_lounge, "reception"),
            "lmw_status": new_lmw, "demo_status": new_demo,
            "ready_to_meet_gurudev": new_ready, "met_gurudev": new_guru
        }
        if new_pic:
            update_data["photo_data"] = base64.b64encode(new_pic.getvalue()).decode()
            
        conn.table("guests").update(update_data).eq("id", guest['id']).execute()
        st.rerun()

    if btn_col3.button("✅ Complete", type="primary", use_container_width=True):
        conn.table("guests").update({"jai_gurudev": True}).eq("id", guest['id']).execute()
        st.rerun()


# ==========================================
#          MAIN DASHBOARD (LIGHTWEIGHT)
# ==========================================
@st.fragment(run_every="10s")
def team_dashboard():
    # Removed UTC date boundaries. Applied NULL safety checks.
    res = (
        conn.table("guests")
        .select("*")
        .eq("is_active", True)
        .or_("jai_gurudev.eq.false,jai_gurudev.is.null")
        .order("created_at")
        .execute()
    )
    active_guests = res.data

    if not active_guests:
        st.success("No active guests currently waiting. Take a breather! ☕")
        return
        
    selected_view = st.pills("Select Station", ["All"] + UI_OPTIONS, default="All", label_visibility="collapsed")
    search_query = st.text_input("🔍 Search Guest...", "", placeholder="Type a name to filter...")
    st.write("---")

    room_order = {"reception": 0, "lounge1": 1, "lounge2": 2, "lounge3": 3, "lounge4": 4, "br": 5, "lounge5": 6, "gmr": 7}
    active_guests.sort(key=lambda g: (room_order.get(g.get('lounge', 'reception'), 99), g['created_at']))

    for guest in active_guests:
        guest_ui_lounge = ZONES_DB_TO_UI.get(guest.get('lounge'), "Unassigned")
        if (selected_view == "All" or guest_ui_lounge == selected_view) and (search_query.lower() in guest['guest_name'].lower()):
            
            bg_color, text_color = COLOR_MAP.get(guest_ui_lounge, ("#E0E0E0", "#000000"))

            with st.container(border=True):
                col_info, col_btn = st.columns([4, 1])
                
                with col_info:
                    st.markdown(
                        f'<div style="background-color: {bg_color}; color: {text_color}; padding: 4px; border-radius: 4px; font-weight: bold; font-size: 16px;">'
                        f'👤 {guest["guest_name"]} &nbsp;|&nbsp; 📍 {guest_ui_lounge}</div>', 
                        unsafe_allow_html=True
                    )
                    
                    status = []
                    if guest.get('lmw_status') and guest.get('lmw_status') != 'Not yet': status.append(f"📺 LMW: {guest.get('lmw_status')}")
                    if guest.get('demo_status') and guest.get('demo_status') != 'Not yet': status.append(f"💻 Demo: {guest.get('demo_status')}")
                    if guest.get('ready_to_meet_gurudev'): status.append("⏳ Ready")
                    if status:
                        st.caption(" • ".join(status))
                
                with col_btn:
                    if st.button("✏️", key=f"open_{guest['id']}", use_container_width=True):
                        guest_action_modal(guest)

team_dashboard()
