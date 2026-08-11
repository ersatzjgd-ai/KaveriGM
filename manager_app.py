import streamlit as st
from st_supabase_connection import SupabaseConnection
import base64
from datetime import datetime
import tempfile
import os
from fpdf import FPDF

# --- CONFIG ---
st.set_page_config(page_title="Kaveri GM - Manager", layout="centered", initial_sidebar_state="collapsed")

conn = st.connection("supabase", type=SupabaseConnection)
today_start = f"{datetime.now().strftime('%Y-%m-%d')}T00:00:00"

# --- ZONES & TRANSLATIONS ---
ZONES_DB_TO_UI = {
    "reception": "Unassigned", "lounge1": "L1", "lounge2": "L2", "lounge3": "L3",
    "lounge4": "L4", "lounge5": "L5", "br": "BR", "gmr": "GMR",
    "passageway_top": "Top Hallway", "passageway_right_a": "Right Hallway A",
    "passageway_right_b": "Right Hallway B", None: "Unassigned", "": "Unassigned"
}
ZONES_UI_TO_DB = {v: k for k, v in ZONES_DB_TO_UI.items() if k not in [None, ""]}
ZONES_UI_TO_DB["Unassigned"] = "reception"
UI_OPTIONS = ["Unassigned", "L1", "L2", "L3", "L4", "L5", "BR", "GMR"]

# --- PERSISTENT LOGIN ---
if "manager_logged_in" not in st.session_state:
    st.session_state.manager_logged_in = st.query_params.get("logged_in") == "true"

st.title("👔 Manager Portal")
st.divider()

if not st.session_state.manager_logged_in:
    pwd_input = st.text_input("Enter Admin Password", type="password")
    if st.button("Login", type="primary"):
        if pwd_input == os.environ.get("MANAGER_PASSWORD", "kaveri_admin"):
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
    res = conn.table("guests").select("*").eq("is_active", False).eq("has_left_kaveri", False).gte("created_at", today_start).order("created_at").execute()
    expected_guests = res.data

    search_incoming = st.text_input("🔍 Search Expected Guest...", "", placeholder="Type a name to filter...")
    filtered_expected = [g for g in expected_guests if search_incoming.lower() in g['guest_name'].lower()]

    if not filtered_expected:
        st.info("No incoming guests match.")
    else:
        for guest in filtered_expected:
            with st.container(border=True):
                st.markdown(f"**👤 {guest['guest_name']}**")
                
                # --- ADDED: Tabs for Camera and Upload ---
                with st.expander("📸 Add Photo (Optional)", expanded=False):
                    tab_cam, tab_up = st.tabs(["📷 Camera", "📁 Upload"])
                    with tab_cam:
                        cam_pic = st.camera_input("Take Photo", key=f"cam_{guest['id']}", label_visibility="collapsed")
                    with tab_up:
                        uploaded_pic = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg"], key=f"up_{guest['id']}", label_visibility="collapsed")
                    
                    # Prioritize whichever image source was used
                    pic = cam_pic if cam_pic else uploaded_pic
                
                selected_ui = st.pills("Assign Lounge", UI_OPTIONS, key=f"mgr_l_{guest['id']}", label_visibility="collapsed")
                
                if selected_ui:
                    db_zone = ZONES_UI_TO_DB.get(selected_ui, "reception")
                    update_data = {"is_active": True, "lounge": db_zone}
                    
                    if pic is not None:
                        update_data["photo_data"] = base64.b64encode(pic.getvalue()).decode()
                        
                    conn.table("guests").update(update_data).eq("id", guest['id']).execute()
                    st.toast(f"{guest['guest_name']} checked in ({selected_ui})!")
                    st.rerun()

    st.write("---") 

    st.subheader("🟢 Arrived Guests")
    res_active = conn.table("guests").select("*").eq("is_active", True).or_("jai_gurudev.eq.false,jai_gurudev.is.null").gte("created_at", today_start).order("created_at").execute()
    mgr_active_guests = res_active.data
    
    if not mgr_active_guests:
        st.info("No guests are currently active inside the building.")
    else:
        for ag in mgr_active_guests:
            col_name, col_undo = st.columns([3, 1])
            display_lounge = ZONES_DB_TO_UI.get(ag.get('lounge'), "Unassigned")
            col_name.markdown(f"**{ag['guest_name']}** | Lounge: **{display_lounge}**")
            if col_undo.button("↩️ Undo", key=f"undo_{ag['id']}"):
                conn.table("guests").update({"is_active": False}).eq("id", ag['id']).execute()
                st.rerun()

    st.write("---") 

    st.subheader("➕ Add Expected Guests")
    with st.form("add_guest_form", clear_on_submit=True):
        new_guests_text = st.text_area(
            "Guest Names*", 
            placeholder="Enter guest names (one per line)\nExample:\nJohn Doe\nJane Smith", 
            height=150
        )
        
        if st.form_submit_button("➕ Add Guests", type="primary", use_container_width=True):
            if new_guests_text.strip():
                guest_names = [name.strip() for name in new_guests_text.split('\n') if name.strip()]
                
                if guest_names:
                    new_guests_payload = [
                        {
                            "guest_name": name,
                            "is_active": False,
                            "has_left_kaveri": False,
                            "jai_gurudev": False,
                            "lounge": "reception"
                        }
                        for name in guest_names
                    ]
                    
                    conn.table("guests").insert(new_guests_payload).execute()
                    st.toast(f"✅ Successfully added {len(guest_names)} expected guests!")
                    st.rerun()
            else:
                st.error("Please enter at least one guest name.")

    st.write("---")

    st.subheader("📄 Daily PDF Report")
    def generate_pdf_report(guests):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "Kaveri Guest Management Report", ln=True, align="C")
        pdf.set_font("Arial", "", 10)
        pdf.cell(0, 8, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align="C")
        pdf.ln(5)
        pdf.set_font("Arial", "B", 10)
        pdf.cell(50, 8, "Guest Name", border=1)
        pdf.cell(30, 8, "Lounge", border=1)
        pdf.cell(30, 8, "LMW", border=1)
        pdf.cell(30, 8, "IP Demo", border=1)
        pdf.cell(40, 8, "Met Gurudev", border=1, ln=True)

        pdf.set_font("Arial", "", 9)
        for g in guests:
            display_lounge = ZONES_DB_TO_UI.get(g.get("lounge"), "Unassigned")
            pdf.cell(50, 8, str(g.get("guest_name", ""))[:25], border=1)
            pdf.cell(30, 8, str(display_lounge), border=1)
            pdf.cell(30, 8, str(g.get("lmw_status", "Not yet")), border=1)
            pdf.cell(30, 8, str(g.get("demo_status", "Not yet")), border=1)
            pdf.cell(40, 8, "Yes" if g.get("met_gurudev") else "No", border=1, ln=True)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            pdf.output(tmp.name)
            tmp_path = tmp.name
        with open(tmp_path, "rb") as f:
            pdf_bytes = f.read()
        os.remove(tmp_path)
        return pdf_bytes

    if st.button("📥 Generate PDF Report", use_container_width=True):
        res_all = conn.table("guests").select("*").gte("created_at", today_start).order("created_at").execute()
        if res_all.data:
            st.download_button("💾 Download PDF", data=generate_pdf_report(res_all.data), file_name=f"guests_{datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf", use_container_width=True)
        else:
            st.warning("No guest data today.")
