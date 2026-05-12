import streamlit as st
from st_supabase_connection import SupabaseConnection
import urllib.parse

# --- CONFIG ---
st.set_page_config(page_title="Guest Tracker", layout="centered")

# Initialize Supabase Connection
# Ensure SUPABASE_URL and SUPABASE_KEY are in your .streamlit/secrets.toml
conn = st.connection("supabase", type=SupabaseConnection)

# --- APP LOGIC ---
st.title("🏛️ Guest Status Tracker")

# 1. Session Selection
session_choice = st.radio("Current Session", ["Morning", "Evening"], horizontal=True)

# 2. Fetch Guests for the selected session
# Assuming you have a column 'session' and 'has_left' in your table
response = conn.table("guests").select("*").eq("session_type", session_choice).execute()
guests = response.data

if not guests:
    st.info(f"No guests listed for the {session_choice} session.")
else:
    for guest in guests:
        # Each guest gets an expandable "Card" for mobile clarity
        with st.expander(f"👤 {guest['guest_name']} - {guest['lounge'] or 'No Lounge'}"):
            
            # Layout for status updates
            lounge = st.selectbox("Lounge", ["L1", "L2", "L3", "BR", "L5"], 
                                 index=0, key=f"lounge_{guest['id']}")
            
            c1, c2 = st.columns(2)
            video = c1.toggle("LMW Video", value=guest.get('video_watched', False), key=f"vid_{guest['id']}")
            ip_demo = c2.toggle("IP Demo", value=guest.get('ip_demo', False), key=f"ip_{guest['id']}")
            
            c3, c4 = st.columns(2)
            gurudev = c3.toggle("Met Gurudev", value=guest.get('met_gurudev', False), key=f"guru_{guest['id']}")
            gift = c4.toggle("Gift Given", value=guest.get('gift_given', False), key=f"gift_{guest['id']}")
            
            left = st.toggle("Left Kaveri (Checkout)", value=guest.get('has_left', False), key=f"left_{guest['id']}")

            # Update Button
            if st.button("Update & Generate WhatsApp", key=f"upd_{guest['id']}", use_container_width=True):
                # 1. Update Supabase
                conn.table("guests").update({
                    "lounge": lounge,
                    "video_watched": video,
                    "ip_demo": ip_demo,
                    "met_gurudev": gurudev,
                    "gift_given": gift,
                    "has_left": left
                }).eq("id", guest['id']).execute()

                # 2. Construct WhatsApp Message
                status_emoji = "✅" if left else "📍 In Office"
                msg = (
                    f"*Guest Status Update*\n"
                    f"👤 *Name:* {guest['guest_name']}\n"
                    f"🛋️ *Lounge:* {lounge}\n"
                    f"📺 *LMW Video:* {'Yes' if video else 'No'}\n"
                    f"💻 *IP Demo:* {'Yes' if ip_demo else 'No'}\n"
                    f"🙏 *Met Gurudev:* {'Yes' if gurudev else 'No'}\n"
                    f"🎁 *Gift Given:* {'Yes' if gift else 'No'}\n"
                    f"🚪 *Status:* {status_emoji}"
                )
                
                # Encode for URL
                encoded_msg = urllib.parse.quote(msg)
                wa_url = f"https://wa.me/?text={encoded_msg}"
                
                st.success("Updated in Database!")
                st.link_button("📲 Share to WhatsApp Group", wa_url, use_container_width=True)
