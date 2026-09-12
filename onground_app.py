import streamlit as st
from st_supabase_connection import SupabaseConnection
import urllib.parse
import base64
from datetime import datetime
import httpx

# --- CONFIG ---
st.set_page_config(page_title="Kaveri GM - Team", layout="centered", initial_sidebar_state="collapsed")

conn = st.connection("supabase", type=SupabaseConnection)
today_start = f"{datetime.now().strftime('%Y-%m-%d')}T00:00:00"

# --- NETWORK FAULT TOLERANCE ---
def safe_execute(query):
    """Catches stale idle connections and forces a fresh reconnect on the fly."""
    try:
        return query.execute()
    except (httpx.RemoteProtocolError, Exception):
        return query.execute()

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
#    INDIVIDUAL GUEST MODAL 
# ==========================================
@st.dialog("Manage Guest")
def guest_action_modal(base_guest):
    try:
        res = safe_execute(conn.table("guests").select("*").eq("id", base_guest['id']))
        guest = res.data[0] if res.data else base_guest
    except Exception:
        guest = base_guest 
    
    col_lounge, col_photo = st.columns([3, 2])
    
    with col_lounge:
        current_ui_lounge = ZONES_DB_TO_UI.get(guest.get('lounge'), "Unassigned")
        lounge_list = UI_OPTIONS.copy()
        if current_ui_lounge not in lounge_list:
            lounge_list.insert(0, current_ui_lounge)
            
        new_lounge_ui = st.selectbox("Update Lounge:", options=lounge_list, index=lounge_list.index(current_ui_lounge), label_visibility="collapsed", key=f"lounge_{guest['id']}")
        new_lounge_db = ZONES_UI_TO_DB.get(new_lounge_ui, "reception")
        
        if new_lounge_db != guest.get('lounge'):
            safe_execute(conn.table("guests").update({"lounge": new_lounge_db}).eq("id", guest['id']))
            guest['lounge'] = new_lounge_db 
    
    with col_photo:
        with st.popover("📸 View Photo", use_container_width=True):
            if guest.get('photo_data'):
                st.image(base64.b64decode(guest['photo_data']), use_container_width=True)
            else:
                st.info("Photo not Uploaded for this guest.")
                
            new_pic = st.camera_input("Update Photo", label_visibility="collapsed", key=f"cam_{guest['id']}")
            if new_pic:
                pic_b64 = base64.b64encode(new_pic.getvalue()).decode()
                if pic_b64 != guest.get('photo_data'):
                    safe_execute(conn.table("guests").update({"photo_data": pic_b64}).eq("id", guest['id']))
                    guest['photo_data'] = pic_b64
                    st.success("✅ Saved!")

    c1, c2 = st.columns(2)
    with c1:
        current_lmw = guest.get('lmw_status') if guest.get('lmw_status') else 'Not yet'
        new_lmw = st.segmented_control("📺 LMW", ["Not yet", "Started", "Done"], default=current_lmw, key=f"lmw_{guest['id']}")
        if new_lmw and new_lmw != current_lmw:
            safe_execute(conn.table("guests").update({"lmw_status": new_lmw}).eq("id", guest['id']))
            guest['lmw_status'] = new_lmw

    with c2:
        current_demo = guest.get('demo_status') if guest.get('demo_status') else 'Not yet'
        new_demo = st.segmented_control("💻 IP Demo", ["Not yet", "Started", "Done"], default=current_demo, key=f"demo_{guest['id']}")
        if new_demo and new_demo != current_demo:
            safe_execute(conn.table("guests").update({"demo_status": new_demo}).eq("id", guest['id']))
            guest['demo_status'] = new_demo

    c3, c4 = st.columns(2)
    with c3:
        new_ready = st.toggle("⏳ Ready for Vyas", value=bool(guest.get('ready_to_meet_gurudev', False)), key=f"ready_{guest['id']}")
        if new_ready != bool(guest.get('ready_to_meet_gurudev', False)):
            safe_execute(conn.table("guests").update({"ready_to_meet_gurudev": new_ready}).eq("id", guest['id']))
            guest['ready_to_meet_gurudev'] = new_ready

    with c4:
        new_guru = st.toggle("🤝 Met Gurudev", value=bool(guest.get('met_gurudev', False)), key=f"guru_{guest['id']}")
        if new_guru != bool(guest.get('met_gurudev', False)):
            safe_execute(conn.table("guests").update({"met_gurudev": new_guru}).eq("id", guest['id']))
            guest['met_gurudev'] = new_guru

    st.markdown("<br>", unsafe_allow_html=True) 
    btn_col1, btn_col2 = st.columns(2)
    
    msg = f"*{new_lounge_ui}*\n{guest['guest_name']}\n📺 LMW: {guest.get('lmw_status', 'Not yet')}\n💻 IP Demo: {guest.get('demo_status', 'Not yet')}\n⏳ Ready for Vyas: {'✅' if guest.get('ready_to_meet_gurudev') else '❌'}\n🤝 Met Gurudev: {'✅' if guest.get('met_gurudev') else '❌'}"
    wa_url = f"https://wa.me/?text={urllib.parse.quote(msg)}"
    btn_col1.link_button("📲 Share via WhatsApp", wa_url, use_container_width=True)
    
    is_done = bool(guest.get('jai_gurudev', False))
    btn_label = "↩️ Undo Complete Visit" if is_done else "✅ Complete Visit"
    
    if btn_col2.button(btn_label, type="primary" if not is_done else "secondary", use_container_width=True, key=f"complete_{guest['id']}"):
        safe_execute(conn.table("guests").update({"jai_gurudev": not is_done}).eq("id", guest['id']))
        st.rerun() 

# ==========================================
#    BULK GUEST MODAL 
# ==========================================
@st.dialog("⚡ Bulk Update Guests")
def bulk_action_modal(active_guests):
    guest_ids = [g['id'] for g in active_guests]
    id_to_name = {g['id']: g['guest_name'] for g in active_guests}
    
    selected_ids = st.multiselect(
        "1. Select Guests to Update:", 
        options=guest_ids, 
        format_func=lambda x: id_to_name[x],
        placeholder="Choose one or more guests..."
    )
    
    st.markdown("**2. Set New Statuses** *(Leave as 'No Change' to keep current state)*")
    
    new_lounge_ui = st.selectbox("Update Lounge:", ["No Change"] + UI_OPTIONS, key="bulk_lounge")
        
    c1, c2 = st.columns(2)
    with c1:
        new_lmw = st.segmented_control("📺 LMW", ["No Change", "Not yet", "Started", "Done"], default="No Change", key="bulk_lmw")
    with c2:
        new_demo = st.segmented_control("💻 IP Demo", ["No Change", "Not yet", "Started", "Done"], default="No Change", key="bulk_demo")
        
    c3, c4 = st.columns(2)
    with c3:
        new_ready = st.radio("⏳ Ready for Vyas", ["No Change", "Yes", "No"], horizontal=True, key="bulk_ready")
    with c4:
        new_guru = st.radio("🤝 Met Gurudev", ["No Change", "Yes", "No"], horizontal=True, key="bulk_guru")
        
    complete_visit = st.toggle("✅ Complete Visit for Selected (Move to DONE)", key="bulk_complete")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🚀 Apply Bulk Updates", type="primary", use_container_width=True):
        if not selected_ids:
            st.error("Please select at least one guest from the dropdown.")
            return
            
        update_payload = {}
        if new_lounge_ui != "No Change":
            update_payload["lounge"] = ZONES_UI_TO_DB.get(new_lounge_ui, "reception")
        if new_lmw != "No Change" and new_lmw is not None:
            update_payload["lmw_status"] = new_lmw
        if new_demo != "No Change" and new_demo is not None:
            update_payload["demo_status"] = new_demo
        if new_ready != "No Change":
            update_payload["ready_to_meet_gurudev"] = (new_ready == "Yes")
        if new_guru != "No Change":
            update_payload["met_gurudev"] = (new_guru == "Yes")
        if complete_visit:
            update_payload["jai_gurudev"] = True
            
        if update_payload:
            for gid in selected_ids:
                safe_execute(conn.table("guests").update(update_payload).eq("id", gid))
            st.rerun()
        else:
            st.warning("No status changes were selected.")


# ==========================================
#          MAIN DASHBOARD 
# ==========================================
@st.fragment(run_every="10s")
def team_dashboard():
    try:
        res = safe_execute(
            conn.table("guests")
            .select("id, guest_name, is_active, has_left_kaveri, jai_gurudev, lounge, lmw_status, demo_status, ready_to_meet_gurudev, met_gurudev, created_at")
            .eq("is_active", True)
            .gte("created_at", today_start)
        )
        all_active = res.data
    except Exception:
        return # Skip this 10-second tick if internet fully drops

    if not all_active:
        st.success("No active guests currently waiting. Take a breather! ☕")
        return
        
    selected_view = st.pills("Select Station", ["All"] + UI_OPTIONS + ["DONE"], default="All", label_visibility="collapsed")
    
    pending_guests = [g for g in all_active if not g.get('jai_gurudev')]
    completed_guests = [g for g in all_active if g.get('jai_gurudev')]
    
    col_search, col_bulk_btn = st.columns([3, 2])
    with col_search:
        search_query = st.text_input("🔍 Search Guest...", "", placeholder="Type a name to filter...", label_visibility="collapsed")
    with col_bulk_btn:
        if st.button("⚡ Bulk Update Guests", type="primary", use_container_width=True):
            bulk_action_modal(pending_guests)
    
    if selected_view not in ["All", "DONE"]:
        lounge_guests = [g for g in pending_guests if ZONES_DB_TO_UI.get(g.get('lounge'), "Unassigned") == selected_view]
        
        if lounge_guests:
            with st.popover(f"📢 WhatsApp Broadcast ({selected_view})", use_container_width=True):
                ready_guests = [g for g in lounge_guests if g.get('ready_to_meet_gurudev')]
                if ready_guests:
                    ready_lines = [f"*{selected_view} - Ready for Vyas*"]
                    for g in ready_guests:
                        ready_lines.append(f"👤 {g['guest_name']}")
                    wa_ready = f"https://wa.me/?text={urllib.parse.quote('\n'.join(ready_lines))}"
                    st.link_button("📲 'Ready for Vyas' List", wa_ready, use_container_width=True)
                else:
                    st.info("No guests marked 'Ready'.")
                
                full_lines = [f"*{selected_view} - Full Status Update*"]
                for g in lounge_guests:
                    sts = []
                    if g.get('lmw_status') not in [None, 'Not yet']: sts.append(f"LMW: {g.get('lmw_status')}")
                    if g.get('demo_status') not in [None, 'Not yet']: sts.append(f"Demo: {g.get('demo_status')}")
                    if g.get('ready_to_meet_gurudev'): sts.append("⏳ Ready")
                    st_str = ", ".join(sts) if sts else "Waiting"
                    full_lines.append(f"👤 {g['guest_name']} ({st_str})")
                
                wa_full = f"https://wa.me/?text={urllib.parse.quote('\n'.join(full_lines))}"
                st.link_button("📲 Full Lounge Status", wa_full, use_container_width=True)

    st.write("---")

    if selected_view == "DONE":
        display_guests = completed_guests
    else:
        display_guests = pending_guests

    display_guests.sort(key=lambda g: g['created_at'])

    if selected_view == "DONE" and not display_guests:
        st.info("No visits completed yet today.")
        return

    for guest in display_guests:
        guest_ui_lounge = ZONES_DB_TO_UI.get(guest.get('lounge'), "Unassigned")
        
        if (selected_view in ["All", "DONE"] or guest_ui_lounge == selected_view) and (search_query.lower() in guest['guest_name'].lower()):
            
            bg_color, text_color = COLOR_MAP.get(guest_ui_lounge, ("#E0E0E0", "#000000")) if selected_view != "DONE" else ("#D1D5DB", "#1F2937")

            with st.container(border=True):
                col_info, col_btn = st.columns([4, 1])
                
                with col_info:
                    st.markdown(
                        f'<div style="background-color: {bg_color}; color: {text_color}; padding: 4px; border-radius: 4px; font-weight: bold; font-size: 16px;">'
                        f'👤 {guest["guest_name"]} &nbsp;|&nbsp; 📍 {guest_ui_lounge} {" (DONE)" if selected_view == "DONE" else ""}</div>', 
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
