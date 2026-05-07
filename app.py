import streamlit as st
import requests
import threading
import telebot
from supabase import create_client, Client

# --- CONFIGURATION ---
st.set_page_config(page_title="Lounge Manager", layout="centered", initial_sidebar_state="collapsed")
LOUNGES = ["L1", "L2", "L3", "BR", "L5"]

# --- INITIALIZE SUPABASE ---
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_supabase()

# --- THE BACKGROUND LISTENER (FOR THE KITCHEN) ---
# @st.cache_resource ensures this thread only starts ONCE when the server wakes up.
# Otherwise, Streamlit would spawn a new bot every time you click a button, causing a crash.
@st.cache_resource
def start_telegram_listener():
    bot = telebot.TeleBot(st.secrets["TELEGRAM_BOT_TOKEN"])
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith('serve_'))
    def handle_serve_button(call):
        lounge = call.data.split('_')[1]
        try:
            # 1. Update Supabase
            supabase.table("lounge_status").upsert({"lounge": lounge, "status": "Served"}).execute()
            
            # 2. Update the Telegram message
            new_text = f"✅ **Served**\n🛋️ Lounge: {lounge} has received water/refreshments."
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=new_text)
            
            bot.answer_callback_query(call.id, text=f"{lounge} marked as served!")
        except Exception as e:
            bot.answer_callback_query(call.id, text="Error updating database.")
            print(f"Listener Error: {e}")

    # Run the bot in a background thread so it doesn't freeze the Streamlit UI
    def run_bot():
        print("Starting Telegram listener thread...")
        bot.infinity_polling()
        
    thread = threading.Thread(target=run_bot, daemon=True)
    thread.start()
    return thread

# Start the background listener immediately
start_telegram_listener()


# --- FUNCTIONS (FOR THE MANAGER) ---
def fetch_status():
    """Fetches the live status of all lounges from Supabase."""
    response = supabase.table("lounge_status").select("*").execute()
    return {row['lounge']: row for row in response.data}

def send_telegram_async(lounge, guests):
    """Sends the interactive message to the kitchen."""
    def _send():
        try:
            token = st.secrets["TELEGRAM_BOT_TOKEN"]
            chat_id = st.secrets["TELEGRAM_CHAT_ID"]
            message = f"🔔 **New Arrival**\n🛋️ Lounge: {lounge}\n👥 Guests: {guests}\n\n🔴 Needs water/refreshments!"
            
            reply_markup = {"inline_keyboard": [[{"text": "✅ Mark as Served", "callback_data": f"serve_{lounge}"}]]}
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": message, "reply_markup": reply_markup}, timeout=5)
        except Exception:
            pass 
    threading.Thread(target=_send).start()

def update_lounge(lounge, guests):
    """Writes to Supabase and triggers the Telegram alert."""
    supabase.table("lounge_status").upsert({
        "lounge": lounge,
        "guest_count": guests,
        "status": "Waiting"
    }).execute()
    send_telegram_async(lounge, guests)


# --- UI: MAIN DASHBOARD ---
st.title("☕ Kitchen Dispatch")

db_state = fetch_status()

if st.button("🔄 Refresh Live Status", use_container_width=True):
    st.rerun()

st.write("")

# Generate individual lounge cards
for lounge in LOUNGES:
    lounge_data = db_state.get(lounge, {"guest_count": 0, "status": "Empty"})
    count = lounge_data["guest_count"]
    status = lounge_data["status"]
    
    status_icon = "🟢 Served" if status == "Served" else "🔴 Waiting" if status == "Waiting" else "⚪ Empty"
    
    with st.container(border=True):
        st.subheader(f"🛋️ {lounge}  |  {status_icon} ({count} guests)")
        
        selected_guests = st.pills("Guests", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], key=f"pills_{lounge}", label_visibility="collapsed")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            if st.button(f"SEND 🚀", key=f"btn_{lounge}", type="primary", use_container_width=True):
                if selected_guests:
                    update_lounge(lounge, selected_guests)
                    st.success(f"Sent!")
                    st.rerun() 
                else:
                    st.warning("Tap a number first.")
        with col2:
            if st.button("Clear", key=f"clear_{lounge}", use_container_width=True):
                supabase.table("lounge_status").upsert({"lounge": lounge, "guest_count": 0, "status": "Empty"}).execute()
                st.rerun()

st.divider()

if st.button("🚨 End of Day: Clear All Lounges", use_container_width=True):
    for lounge in LOUNGES:
        supabase.table("lounge_status").upsert({"lounge": lounge, "guest_count": 0, "status": "Empty"}).execute()
    st.toast("All lounges cleared!")
    st.rerun()
