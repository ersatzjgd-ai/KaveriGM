import streamlit as st
from st_supabase_connection import SupabaseConnection
import urllib.parse
import random
import string

# --- CONFIG ---
st.set_page_config(page_title="Kaveri Guest Manager", layout="centered", initial_sidebar_state="collapsed")

# Initialize Supabase Connection
conn = st.connection("supabase", type=SupabaseConnection)

# --- HELPER FUNCTIONS ---
def generate_password(length=6):
    """Generates a quick, readable password for guests."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# --- UI: ROLE SELECTOR ---
st.title("🏛️ Kaveri Command")
# A fast toggle switch at the top of the app
role = st.segmented_control("Select Role", ["On-Ground Staff 🏃", "Manager 👔"], default="On-Ground Staff 🏃")
st.divider()

# ==========================================
#              MANAGER UI
# ==========================================
if role == "Manager 👔":
    st.subheader("📥 Incoming Guests")
    st.caption("Check-in expected guests, assign lounges, and generate access.")
    
    # Fetch guests who haven't left and aren't active yet (Expected guests)
    res = conn.table("guests").select("*").eq("is_active", False).eq("has_left_kaveri", False).execute()
    expected_guests = res.data

    if not expected_guests:
        st.info("No new expected guests at the moment.")
    else:
        for guest in expected_guests:
            with st.expander(f"👤 {guest['guest_name']} ({guest['session_type']})"):
                # Manager Actions
                lounge_choice = st.selectbox("Assign Lounge", ["L1", "L2", "L3", "BR", "L5"], key=f"mgr_l_{guest['id']}")
                
                col1, col2 = st.columns([3, 1])
                new_pass = col1.text_input("Access Password", value=generate_password(), key=f"mgr_p_{guest['id']}")
                
                if st.button("Mark as ACTIVE ✅", key=f"mgr_btn_{guest['id']}", type="primary", use_container_width=True):
                    # Update DB to make them active for the ground staff
                    conn.table("guests").update({
                        "is_active": True,
                        "lounge": lounge_choice,
                        "access_password": new_pass
                    }).eq("id", guest['id']).execute()
                    
                    st.toast(f"{guest['guest_name']} is now Active in {lounge_choice}!")
                    st.rerun()

# ==========================================
#           ON-GROUND STAFF UI
# ==========================================
elif role == "On-Ground Staff 🏃":
    st.subheader("📍 Active Guests")
    
    # Fetch ONLY guests who are currently Active in the building
    res = conn.table("guests").select("*").eq("is_active", True).eq("has_left_kaveri", False).execute()
    active_guests = res.data

    if not active_guests:
        st.success("No active guests currently in the building! Take a breather. ☕")
    else:
        # Create a dictionary for the dropdown menu
        guest_dict = {f"{g['guest_name']} - {g['lounge']}": g for g in active_guests}
        
        # Dropdown menu as requested
        selected_guest_label = st.selectbox("Select Guest to Update:", options=list(guest_dict.keys()))
        selected_guest = guest_dict[selected_guest_label]
        g_id = selected_guest['id']

        # Container for the selected guest's actions
        with st.container(border=True):
            st.markdown(f"### {selected_guest['guest_name']}")
            st.caption(f"**Lounge:** {selected_guest['lounge']} | **WiFi:** `{selected_guest.get('access_password', 'N/A')}`")
            
            # Status Toggles
            c1, c2 = st.columns(2)
            video = c1.toggle("📺 LMW Video", value=selected_guest.get('video_watched', False))
            ip_demo = c2.toggle("💻 IP Demo", value=selected_guest.get('ip_demo_done', False))
            
            c3, c4 = st.columns(2)
            gurudev = c3.toggle("🙏 Met Gurudev", value=selected_guest.get('met_gurudev', False))
            gift = c4.toggle("🎁 Gift Given", value=selected_guest.get('gift_given', False))
            
            st.divider()
            
            # Left Building Toggle (Checkout)
            left_building = st.toggle("🚪 Guest Left Kaveri (Checkout)", value=False)

            if st.button("💾 Save Status & WhatsApp", type="primary", use_container_width=True):
                # 1. Update Database
                conn.table("guests").update({
                    "video_watched": video,
                    "ip_demo_done": ip_demo,
                    "met_gurudev": gurudev,
                    "gift_given": gift,
                    "has_left_kaveri": left_building,
                    "is_active": not left_building # If they left, they are no longer active
                }).eq("id", g_id).execute()

                st.toast("Database Updated!")

                # 2. WhatsApp Generation
                status_emoji = "✅ Departed" if left_building else "📍 In Session"
                msg = (
                    f"*Status Update: {selected_guest['guest_name']}*\n"
                    f"Lounge: {selected_guest['lounge']}\n"
                    f"📺 Video: {'Yes' if video else 'No'}\n"
                    f"💻 Demo: {'Yes' if ip_demo else 'No'}\n"
                    f"🙏 Gurudev: {'Yes' if gurudev else 'No'}\n"
                    f"🎁 Gift: {'Yes' if gift else 'No'}\n"
                    f"Status: {status_emoji}"
                )
                wa_url = f"https://wa.me/?text={urllib.parse.quote(msg)}"
                
                # Show the WhatsApp Link
                st.link_button("📲 Share to WhatsApp", wa_url, use_container_width=True)
                
                # If they checked out, rerun to clear them from the active list
                if left_building:
                    st.rerun()
