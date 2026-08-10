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

st.title("🏃 Lounge Team")

# ==========================================
#    MODAL DIALOG FUNCTION (INSTANT SAVE)
# ==========================================
@st.dialog("Manage Guest")
def guest_action_modal(guest):
    
    col_lounge, col_photo = st.columns([3, 1])
    
    # --- LOUNGE UPDATE ---
    with col_lounge:
        current_ui_lounge = ZONES_DB_TO_UI.get(guest.get('lounge'), "Unassigned")
        lounge_list = UI_OPTIONS.copy()
        if current_ui_lounge not in lounge_list:
            lounge_list.insert(0, current_ui_lounge)
            
        new_lounge_ui = st.selectbox("Update Lounge:", options=lounge_list, index=lounge_list.index(current_ui_lounge), label_visibility="collapsed")
        new_lounge_db = ZONES_UI_TO_DB.get(new_lounge_ui, "reception")
        
        # Auto-save to DB instantly
        if new_lounge_db != guest.get('lounge'):
            conn.table("guests").update({"lounge": new_lounge_db}).eq("id", guest['id']).execute()
            guest['lounge'] = new_lounge_db 
    
    # --- PHOTO UPDATE ---
    with col_photo:
        with st.popover("📸", use_container_width=True):
            if guest.get('photo_data'):
                st.image(base64.b64decode(guest['photo_data']), use_container_width=True)
            else:
                st.info("No photo.")
                
            new_pic = st.camera_input("Update Photo", label_visibility="collapsed")
            if new_pic:
                pic_b64 = base64.b64encode(new_pic.getvalue()).decode()
                if pic_b64 != guest.get('photo_data'):
                    conn.table("guests").update({"photo_data": pic_b64}).eq("id", guest['id']).execute()
                    guest['photo_data'] = pic_b64
                    st.success("✅ Saved!")

    # --- STATUS CONTROLS ---
    c1, c2 = st.columns(2)
    with c1:
        current_lmw = guest.get('lmw_status') if guest.get('lmw_status') else 'Not yet'
        new_lmw = st.segmented_control("📺 LMW", ["Not yet", "Started", "Done"], default=current_lmw)
        if new_lmw and new_lmw != current_lmw:
            conn.table("guests").update({"lmw_status": new_lmw}).eq("id", guest['id']).execute()
            guest['lmw_status'] = new_lmw

    with c2:
        current_demo = guest.get('demo_status') if guest.get('demo_status') else 'Not yet'
        new_demo = st.segmented_control("💻 IP Demo", ["Not yet", "Started", "Done"], default=current_demo)
        if new_demo and new_demo != current_demo:
            conn.table("guests").update({"demo_status": new_demo}).eq("id", guest['id']).execute()
            guest['demo_status'] = new_demo

    c3, c4 = st.columns(2)
    with c3:
        new_ready = st.toggle("⏳ Ready for Vyas", value=bool(guest.get('ready_to_meet_gurudev', False)))
        if new_ready != bool(guest.get('ready_to_meet_gurudev', False)):
            conn.table("guests").update({"ready_to_meet_gurudev": new_ready}).eq("id", guest['id']).execute()
            guest['ready_to_meet_gurudev'] = new_ready

    with c4:
        new_guru = st.toggle("🤝 Met Gurudev", value=bool(guest.get('met_gurudev', False)))
        if new_guru != bool(guest.get('met_gurudev', False)):
            conn.table("guests").update({"met_gurudev": new_guru}).eq("id", guest['id']).execute()
            guest['met_gurudev'] = new_guru

    # --- ACTIONS ---
    st.markdown("<br>", unsafe_allow_html=True) 
    btn_col1, btn_col2 = st.columns(2)
    
    # WhatsApp Share
    msg = f"*{new_lounge_ui}*\n{guest['guest_name']}\n📺 LMW: {guest.get('lmw_status', 'Not yet')}\n💻 IP Demo: {guest.get('demo_status', 'Not yet')}\n⏳ Ready for Vyas: {'✅' if guest.get('ready_to_meet_gurudev') else '❌'}\n🤝 Met Gurudev: {'✅' if guest.get('met_gurudev') else '❌'}"
    wa_url = f"https://wa.me/?text={urllib.parse.quote(msg)}"
    btn_col1.link_button("📲 Share via WhatsApp", wa_url, use_container_width=True)
    
    # Complete / Archive Guest
    if btn_col2.button("✅ Complete Visit", type="primary", use_container_width=True):
        conn.table("guests").update({"jai_gurudev": True}).eq("id", guest['id']).execute()
        st.rerun() # Reruns the main app to remove the guest from the list


# ==========================================
#          MAIN DASHBOARD (LIGHTWEIGHT)
# ==========================================
@st.fragment(run_every="10s")
def team_dashboard():
    res = (
        conn.table("guests")
        .select("*")
        .eq("is_active", True)
        .or_("jai_gurudev.eq.false,jai_gurudev.is.null")
        .execute()
    )
    active_guests = res.data

    if not active_guests:
        st.success("No active guests currently waiting. Take a breather! ☕")
        return
        
    selected_view = st.pills("Select Station", ["All"] + UI_OPTIONS, default="All", label_visibility="collapsed")
    search_query = st.text_input("🔍 Search Guest...", "", placeholder="Type a name to filter...")
    st.write("---")

    # FIX: Sort strictly by creation time (when they were expected/entered) to prevent shuffling
    active_guests.sort(key=lambda g: g['created_at'])

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
