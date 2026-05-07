import streamlit as st
import requests
import threading

# --- CONFIGURATION ---
st.set_page_config(page_title="Lounge Manager", layout="centered", initial_sidebar_state="collapsed")

# --- STATE INITIALIZATION ---
# Using a list allows us to easily add more lounges in the future
LOUNGES = ["L1", "L2", "L3", "BR", "L5"]

# Dynamically initialize counts for all lounges to 0
for lounge in LOUNGES:
    state_key = f"{lounge.lower()}_count"
    if state_key not in st.session_state:
        st.session_state[state_key] = 0

# --- FUNCTIONS ---
def send_telegram_async(lounge, guests):
    """Sends the Telegram message in a background thread."""
    def _send():
        try:
            token = st.secrets["TELEGRAM_BOT_TOKEN"]
            chat_id = st.secrets["TELEGRAM_CHAT_ID"]
            message = f"🔔 **New Arrival**\nLounge: {lounge}\nGuests: {guests} (Needs refreshments!)"
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=5)
        except Exception:
            pass 
    threading.Thread(target=_send).start()

def reset_counts():
    """Resets all lounge tracking variables back to zero."""
    for lounge in LOUNGES:
        st.session_state[f"{lounge.lower()}_count"] = 0

# --- UI: MAIN TITLE ---
st.title("☕ Kitchen Dispatch")
st.write("Tap a number inside a lounge card to dispatch.")

# --- UI: INDIVIDUAL LOUNGE CARDS ---
# We loop through our list of lounges to generate a card for each one
for lounge in LOUNGES:
    # st.container(border=True) creates a nice visual "card" on the screen
    with st.container(border=True):
        st.subheader(f"🛋️ {lounge}")
        
        # Unique keys are required so Streamlit knows WHICH pill box was tapped
        selected_guests = st.pills(
            "Number of Guests", 
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 
            key=f"pills_{lounge}",
            label_visibility="collapsed" # Hides the label to save vertical space on mobile
        )
        
        if st.button(f"SEND TO KITCHEN 🚀", key=f"btn_{lounge}", type="primary", use_container_width=True):
            if selected_guests:
                # Update local count
                st.session_state[f"{lounge.lower()}_count"] += selected_guests
                
                # Send notification
                send_telegram_async(lounge, selected_guests)
                
                st.success(f"Sent! {selected_guests} guests to {lounge}.")
            else:
                st.warning(f"Tap a number for {lounge} first.")

st.write("") # Spacer

# --- UI: RESET BUTTON ---
if st.button("🔄 Reset All Counts to Zero", use_container_width=True):
    reset_counts()
    st.toast("All lounge counts have been cleared!")

st.divider()

# --- UI: DASHBOARD (MOVED TO BOTTOM) ---
st.subheader("Current Occupancy")

# Creating a 3-column layout for the top row, and 2-column for the bottom row
cols1 = st.columns(3)
cols1[0].metric(label="L1", value=st.session_state.l1_count)
cols1[1].metric(label="L2", value=st.session_state.l2_count)
cols1[2].metric(label="L3", value=st.session_state.l3_count)

cols2 = st.columns(2)
cols2[0].metric(label="BR", value=st.session_state.br_count)
cols2[1].metric(label="L5", value=st.session_state.l5_count)
