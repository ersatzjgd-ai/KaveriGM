import streamlit as st
import requests
import threading

# --- CONFIGURATION ---
# "collapsed" sidebar keeps the mobile screen clear of clutter
st.set_page_config(page_title="Lounge Manager", layout="centered", initial_sidebar_state="collapsed")

# --- STATE INITIALIZATION ---
if "l1_count" not in st.session_state: st.session_state.l1_count = 0
if "l2_count" not in st.session_state: st.session_state.l2_count = 0
if "l3_count" not in st.session_state: st.session_state.l3_count = 0

# --- FUNCTIONS ---
def send_telegram_async(lounge, guests):
    """
    Sends the Telegram message in a background thread. 
    This prevents the app from 'hanging' or slowing down while waiting for Telegram's servers.
    """
    def _send():
        try:
            # Securely pull credentials from Streamlit Secrets
            token = st.secrets["TELEGRAM_BOT_TOKEN"]
            chat_id = st.secrets["TELEGRAM_CHAT_ID"]
            
            message = f"🔔 **New Arrival**\nLounge: {lounge}\nGuests: {guests} (Needs refreshments!)"
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            
            requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=5)
        except Exception:
            # Silently fail in the background to ensure the manager's UI is never disrupted
            pass 
            
    # Fire and forget
    threading.Thread(target=_send).start()

# --- UI: DASHBOARD CARDS ---
st.title("☕ Kitchen Dispatch")

# Three simple cards tracking the current count
cols = st.columns(3)
cols[0].metric(label="L1", value=st.session_state.l1_count)
cols[1].metric(label="L2", value=st.session_state.l2_count)
cols[2].metric(label="L3", value=st.session_state.l3_count)

st.divider()

# --- UI: DATA ENTRY (MOBILE OPTIMIZED) ---
# st.pills provides excellent, large touch targets for mobile screens
selected_lounge = st.pills("Select Lounge", ["L1", "L2", "L3"])
selected_guests = st.pills("Number of Guests", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

st.write("") # Spacer

# Massive button taking up the full container width for easy tapping while moving
if st.button("SEND TO KITCHEN 🚀", type="primary", use_container_width=True):
    if selected_lounge and selected_guests:
        # 1. Update the local dashboard count instantly
        if selected_lounge == "L1": st.session_state.l1_count += selected_guests
        elif selected_lounge == "L2": st.session_state.l2_count += selected_guests
        elif selected_lounge == "L3": st.session_state.l3_count += selected_guests
        
        # 2. Trigger the background Telegram notification
        send_telegram_async(selected_lounge, selected_guests)
        
        # 3. Provide instant visual feedback
        st.success(f"Update sent! {selected_guests} guests marked for {selected_lounge}.")
    else:
        st.warning("Please tap both a lounge and a guest count first.")
