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

# --- PERSISTENT LOGIN (SURVIVES PAGE REFRESH) ---
if "manager_logged_in" not in st.session_state:
    if st.query_params.get("logged_in") == "true":
        st.session_state.manager_logged_in = True
    else:
        st.session_state.manager_logged_in = False

# ==========================================
#         TELEGRAM INTEGRATION ALERT
# ==========================================
def alert_telegram_team(guest_id, guest_name, photo_bytes=None):
    st.error(f"Keys Streamlit can see right now: {list(st.secrets.keys())}")
    
    telegram_token = st.secrets.get("TELEGRAM_BOT_TOKEN")
    group_id = st.secrets.get("TELEGRAM_GROUP_ID")
    
    # Change it to st.error so it shows on your screen!
    if not telegram_token or not group_id:
        st.error("🚨 Missing Telegram Secrets! Check Streamlit Cloud Settings.")
        return

    url = f"https://api.telegram.org/bot{telegram_token}/sendPhoto"
    
    caption = f"🚨 *New Arrival*\n👤 *{guest_name}*\n📍 Lounge: *Unassigned*\n\nPlease assign a lounge:"
    
    reply_markup = {
        "inline_keyboard": [[
            {"text": "L1", "callback_data": f"lng:{guest_id}:L1"},
            {"text": "L2", "callback_data": f"lng:{guest_id}:L2"},
            {"text": "L3", "callback_data": f"lng:{guest_id}:L3"},
            {"text": "BR", "callback_data": f"lng:{guest_id}:BR"},
            {"text": "L5", "callback_data": f"lng:{guest_id}:L5"}
        ]]
    }

    data = {
        "chat_id": group_id,
        "caption": caption,
        "parse_mode": "Markdown",
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
            
        # This will force Streamlit to show the exact Telegram error on the screen
        if res.status_code != 200:
            st.error(f"Telegram API Error: {res.text}")
            
    except Exception as e:
        st.error(f"Failed to send Telegram alert: {e}")

# --- UI: ROLE SELECTOR ---
st.title("🏛️ Kaveri GM")
role = st.segmented_control("Select Role", ["On-Ground Team 🏃", "Manager 👔"], default="On-Ground Team 🏃")
st.divider()

# ==========================================
#            MANAGER UI
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
                    
                    selected_lounge = st.pills("Assign Lounge", ["L1", "L2", "L3", "BR", "L5", "Unassigned"], key=f"mgr_l_{guest['id']}", label_visibility="collapsed")
                    
                    if selected_lounge:
                        update_data = {
                            "is_active": True,
                            "lounge": selected_lounge
                        }
                        
                        if pic is not None:
                            update_data["photo_data"] = base64.b64encode(pic.getvalue()).decode()
                            
                        # 1. Update Database
                        conn.table("guests").update(update_data).eq("id", guest['id']).execute()
                        
                        # 2. Trigger Telegram Alert
                        alert_telegram_team(guest['id'], guest['guest_name'], pic.getvalue() if pic is not None else None)
                        
                        st.toast(f"{guest['guest_name']} checked in ({selected_lounge})!")
                        #st.rerun()

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

        st.write("---")

        # --- 📊 END OF SESSION REPORT WITH PDF EXPORT ---
        with st.expander("📊 View End of Session Report", expanded=False):
            st.subheader("Today's Guest Report")
            st.caption("A summary of all guests scheduled for today and their final statuses.")
            
            report_res = conn.table("guests").select("*").gte("created_at", today_start).order("created_at").execute()
            report_guests = report_res.data
            
            if not report_guests:
                st.info("No guests have been added for today yet.")
            else:
                for rg in report_guests:
                    with st.container(border=True):
                        r_col_img, r_col_info = st.columns([1, 2.5])
                        
                        with r_col_img:
                            if rg.get('photo_data'):
                                st.image(base64.b64decode(rg['photo_data']), use_container_width=True)
                            else:
                                st.info("No Photo", icon="📷")
                                
                        with r_col_info:
                            st.markdown(f"#### 👤 {rg['guest_name']}")
                            st.markdown(f"**Session:** {rg.get('session_type', 'N/A')} | **Lounge:** {rg.get('lounge', 'Not Assigned')}")
                            
                            status_col1, status_col2 = st.columns(2)
                            with status_col1:
                                st.caption("📺 LMW")
                                st.write(f"**{rg.get('lmw_status', 'Not yet')}**")
                                st.caption("💻 IP Demo")
                                st.write(f"**{rg.get('demo_status', 'Not yet')}**")
                            with status_col2:
                                st.caption("🤝 Met Gurudev")
                                st.write("✅ Yes" if rg.get('met_gurudev') else "❌ No")
                                st.caption("🏁 Visit Complete")
                                st.write("✅ Yes" if rg.get('jai_gurudev') else "❌ No")

                def sanitize_text(val):
                    if not val: return ""
                    s = str(val).replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-")
                    return s.encode('latin-1', 'replace').decode('latin-1')

                def generate_pdf(guests_data):
                    pdf = FPDF()
                    pdf.set_auto_page_break(auto=True, margin=15)
                    pdf.add_page()
                    
                    pdf.set_font("Arial", 'B', 16)
                    pdf.cell(0, 10, txt=sanitize_text(f"Kaveri GM - End of Session Report ({datetime.now().strftime('%Y-%m-%d')})"), ln=True, align='C')
                    pdf.ln(5)
                    
                    for g in guests_data:
                        pdf.set_font("Arial", 'B', 12)
                        pdf.cell(0, 8, txt=sanitize_text(f"Guest: {g['guest_name']} ({g.get('session_type', 'N/A')})"), ln=True)
                        
                        pdf.set_font("Arial", '', 10)
                        pdf.cell(0, 6, txt=sanitize_text(f"Lounge: {g.get('lounge', 'Not Assigned')}"), ln=True)
                        
                        lmw = g.get('lmw_status', 'Not yet')
                        demo = g.get('demo_status', 'Not yet')
                        pdf.cell(0, 6, txt=sanitize_text(f"LMW: {lmw} | IP Demo: {demo}"), ln=True)
                        
                        guru = "Yes" if g.get('met_gurudev') else "No"
                        jai = "Yes" if g.get('jai_gurudev') else "No"
                        pdf.cell(0, 6, txt=sanitize_text(f"Met Gurudev: {guru} | Visit Complete: {jai}"), ln=True)
                        
                        if g.get('photo_data'):
                            try:
                                img_bytes = base64.b64decode(g['photo_data'])
                                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                                    tmp_file.write(img_bytes)
                                    tmp_path = tmp_file.name
                                
                                pdf.ln(2)
                                pdf.image(tmp_path, w=35)
                                os.remove(tmp_path)
                            except Exception:
                                pdf.cell(0, 6, txt=sanitize_text("[Error loading photo]"), ln=True)
                                
                        pdf.ln(5)
                        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
                        pdf.ln(5)
                    
                    try:
                        return pdf.output(dest='S').encode('latin-1')
                    except Exception:
                        return bytes(pdf.output())

                st.write("---")
                pdf_bytes = generate_pdf(report_guests)
                st.download_button(
                    label="📥 Download Report as PDF",
                    data=pdf_bytes,
                    file_name=f"Kaveri_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )


# ==========================================
#           ON-GROUND TEAM UI
# ==========================================
elif role == "On-Ground Team 🏃":

    # --- NO-RERUN CALLBACKS (PREVENTS SCROLL JUMPING) ---
    def commit_save(g_id, g_name):
        new_lounge = st.session_state[f"staff_l_{g_id}"]
        update_data = {
            "lounge": new_lounge,
            "lmw_status": st.session_state[f"lmw_{g_id}"],
            "demo_status": st.session_state[f"demo_{g_id}"],
            "ready_to_meet_gurudev": st.session_state[f"ready_{g_id}"],
            "met_gurudev": st.session_state[f"guru_{g_id}"]
        }
        conn.table("guests").update(update_data).eq("id", g_id).execute()
        
        if g_id in st.session_state.initial_lounges:
            st.session_state.initial_lounges[g_id] = new_lounge
            
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
            
        # --- UI: LOUNGE FILTER ---
        selected_view = st.pills("Select your station", ["All", "Unassigned", "L1", "L2", "L3", "BR", "L5"], default="All", key="lounge_tab_selector", label_visibility="collapsed")
        st.write("---")

        # --- 🔒 ANTI-RESHUFFLE LOGIC 🔒 ---
        if "initial_lounges" not in st.session_state:
            st.session_state.initial_lounges = {}
            
        for g in active_guests:
            if g['id'] not in st.session_state.initial_lounges:
                st.session_state.initial_lounges[g['id']] = g.get('lounge') or "Unassigned"
                
        room_order = {"Unassigned": 0, "L1": 1, "L2": 2, "L3": 3, "BR": 4, "L5": 5}
        
        active_guests.sort(key=lambda g: (
            room_order.get(st.session_state.initial_lounges[g['id']], 99),
            g['created_at']
        ))

        search_query = st.text_input("🔍 Search Guest Name...", "", placeholder="Type a name to filter...")

        filtered_guests = []
        for g in active_guests:
            matches_search = search_query.lower() in g['guest_name'].lower()
            guest_current_lounge = g.get('lounge') or "Unassigned"
            matches_lounge = (selected_view == "All") or (guest_current_lounge == selected_view)
            
            if matches_search and matches_lounge:
                filtered_guests.append(g)

        if not filtered_guests:
            if selected_view != "All" and not search_query:
                st.info(f"No active guests currently in {selected_view}.")
            else:
                st.info("No guests match your filters.")

        for guest in filtered_guests:
            current_lounge = guest.get('lounge') or "Unassigned"
            
            color_map = {
                "Unassigned": ("#FFDDC1", "#000000"), 
                "L1": ("#00FFFF", "#000000"),
                "L2": ("#FFFF00", "#000000"),
                "L3": ("#FF00FF", "#FFFFFF"),
                "L5": ("#000000", "#FFFFFF"),
                "BR": ("#E0E0E0", "#000000") 
            }
            bg_color, text_color = color_map.get(current_lounge, ("#E0E0E0", "#000000"))

            with st.container(border=True):
                # Extra-squeezed name card (padding reduced from 8px to 4px)
                st.markdown(
                    f'<div style="background-color: {bg_color}; color: {text_color}; padding: 4px; border-radius: 4px; text-align: center; font-weight: bold; margin-bottom: 5px; font-size: 16px;">'
                    f'👤 {guest["guest_name"]}</div>', 
                    unsafe_allow_html=True
                )
                
                # --- Row 1: Lounge Dropdown & Photo Popover ---
                col_lounge, col_photo = st.columns([3, 1])
                with col_lounge:
                    lounge_options = ["Unassigned", "L1", "L2", "L3", "BR", "L5"]
                    if current_lounge not in lounge_options:
                        lounge_options.insert(0, current_lounge)
                    st.selectbox("Update Lounge:", options=lounge_options, index=lounge_options.index(current_lounge), key=f"staff_l_{guest['id']}", label_visibility="collapsed")
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

                # --- Row 2: Squeezed Horizontal Segmented Controls ---
                # (Captions removed. Labels built directly into the widget to save height)
                c1, c2 = st.columns(2)
                with c1:
                    st.segmented_control("📺 LMW", ["Not yet", "Started", "Done"], default=guest.get('lmw_status', 'Not yet'), key=f"lmw_{guest['id']}", label_visibility="visible")
                with c2:
                    st.segmented_control("💻 IP Demo", ["Not yet", "Started", "Done"], default=guest.get('demo_status', 'Not yet'), key=f"demo_{guest['id']}", label_visibility="visible")

                # --- Row 3: Squeezed Toggles ---
                # (Properly indented under columns to force them horizontally next to each other)
                c3, c4 = st.columns(2)
                with c3:
                    st.toggle("⏳ Ready for Vyas", value=guest.get('ready_to_meet_gurudev', False), key=f"ready_{guest['id']}")
                with c4:
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
                btn_col1, btn_col2, btn_col3 = st.columns(3)
                
                btn_col1.link_button("📲 WhatsApp", wa_url, use_container_width=True)
                btn_col2.button("💾 Save Updates", use_container_width=True, key=f"save_btn_{guest['id']}", on_click=commit_save, args=(guest['id'], guest['guest_name']))
                btn_col3.button("✅ Complete", type="primary", use_container_width=True, key=f"jai_btn_{guest['id']}", on_click=mark_complete, args=(guest['id'], guest['guest_name']))

    team_dashboard()
