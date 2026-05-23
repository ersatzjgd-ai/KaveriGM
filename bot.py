import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from supabase import create_client, Client

# --- CONFIG ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
#      RENDER FREE TIER PORT HACK
# ==========================================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is awake and listening to Telegram!")

def run_dummy_server():
    # Render assigns a PORT environment variable dynamically
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    server.serve_forever()

# Start the dummy web server in a background thread
threading.Thread(target=run_dummy_server, daemon=True).start()

# ==========================================
#            BOT LOGIC BELOW
# ==========================================

# --- KEYBOARD GENERATOR ---
def generate_guest_keyboard(guest):
    markup = InlineKeyboardMarkup(row_width=3)
    g_id = guest['id']
    
    # STATE 1: Unassigned (The Dispatch Screen)
    if not guest.get('lounge') or guest.get('lounge') == 'Unassigned':
        markup.add(
            InlineKeyboardButton("L1", callback_data=f"lng:{g_id}:L1"),
            InlineKeyboardButton("L2", callback_data=f"lng:{g_id}:L2"),
            InlineKeyboardButton("L3", callback_data=f"lng:{g_id}:L3"),
            InlineKeyboardButton("BR", callback_data=f"lng:{g_id}:BR"),
            InlineKeyboardButton("L5", callback_data=f"lng:{g_id}:L5")
        )
        return markup

    # STATE 2: Claimed & Active (The Workflow Toggles)
    lmw_states = {"Not yet": "Started", "Started": "Done", "Done": "Not yet"}
    demo_states = {"Not yet": "Started", "Started": "Done", "Done": "Not yet"}
    
    next_lmw = lmw_states.get(guest.get('lmw_status', 'Not yet'), "Started")
    next_demo = demo_states.get(guest.get('demo_status', 'Not yet'), "Started")
    
    markup.add(
        InlineKeyboardButton(f"📺 LMW: {guest.get('lmw_status', 'Not yet')}", callback_data=f"lmw:{g_id}:{next_lmw}"),
        InlineKeyboardButton(f"💻 Demo: {guest.get('demo_status', 'Not yet')}", callback_data=f"dmo:{g_id}:{next_demo}")
    )
    
    ready_text = "✅ Ready" if guest.get('ready_to_meet_gurudev') else "❌ Ready"
    guru_text = "✅ Met Guru" if guest.get('met_gurudev') else "❌ Met Guru"
    
    markup.add(
        InlineKeyboardButton(ready_text, callback_data=f"rdy:{g_id}:toggle"),
        InlineKeyboardButton(guru_text, callback_data=f"gur:{g_id}:toggle")
    )
    
    markup.add(InlineKeyboardButton("🏁 Complete Visit", callback_data=f"cmp:{g_id}:done"))
    return markup

# --- MESSAGE TEXT GENERATOR ---
def generate_guest_text(guest, updated_by=None):
    if not guest.get('lounge') or guest.get('lounge') == 'Unassigned':
        return f"🚨 *New Arrival*\n👤 *{guest['guest_name']}*\n📍 Lounge: *Unassigned*\n\n👇 *Please claim and assign a lounge:*"
    
    text = f"✅ *Claimed & Assigned to {guest.get('lounge')}*\n"
    text += f"👤 *{guest['guest_name']}*\n\n"
    text += f"📺 LMW: {guest.get('lmw_status', 'Not yet')}\n"
    text += f"💻 IP Demo: {guest.get('demo_status', 'Not yet')}\n"
    text += f"⏳ Ready for Vyas: {'✅' if guest.get('ready_to_meet_gurudev') else '❌'}\n"
    text += f"🤝 Met Gurudev: {'✅' if guest.get('met_gurudev') else '❌'}\n"
    
    if updated_by:
        text += f"\n_Last updated by @{updated_by}_"
        
    return text

# --- SMART EDIT HELPER (Handles both Text and Photo messages) ---
def update_tg_message(call, new_text, new_markup):
    if call.message.content_type == 'text':
        bot.edit_message_text(text=new_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=new_markup)
    else:
        bot.edit_message_caption(caption=new_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=new_markup)

# --- CALLBACK HANDLER ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    action, g_id, value = call.data.split(':')
    user_name = call.from_user.username or call.from_user.first_name
    
    # 1. Fetch current guest state from Supabase
    res = supabase.table("guests").select("*").eq("id", g_id).execute()
    if not res.data:
        bot.answer_callback_query(call.id, "Guest not found in database.", show_alert=True)
        return
    guest = res.data[0]

    # --- 2. RACE CONDITION PREVENTION ---
    if action == "lng" and guest.get('lounge') and guest.get('lounge') != "Unassigned":
        bot.answer_callback_query(call.id, "⚠️ Too late! Already claimed.", show_alert=True)
        new_text = generate_guest_text(guest)
        new_markup = generate_guest_keyboard(guest)
        update_tg_message(call, new_text, new_markup)
        return

    # 3. Determine Update Payload
    update_data = {}
    if action == "lng": update_data = {"lounge": value}
    elif action == "lmw": update_data = {"lmw_status": value}
    elif action == "dmo": update_data = {"demo_status": value}
    elif action == "rdy": update_data = {"ready_to_meet_gurudev": not guest.get('ready_to_meet_gurudev', False)}
    elif action == "gur": update_data = {"met_gurudev": not guest.get('met_gurudev', False)}
    elif action == "cmp": update_data = {"jai_gurudev": True}

    # 4. Update Supabase
    updated_res = supabase.table("guests").update(update_data).eq("id", g_id).execute()
    updated_guest = updated_res.data[0]

    # 5. Update Telegram Message In-Place
    if action == "cmp":
        final_text = f"🏁 *{updated_guest['guest_name']} - Visit Complete*\n_Finalized by @{user_name}_"
        update_tg_message(call, final_text, None)
        bot.answer_callback_query(call.id, "Visit Completed!")
    else:
        new_text = generate_guest_text(updated_guest, updated_by=user_name)
        new_markup = generate_guest_keyboard(updated_guest)
        update_tg_message(call, new_text, new_markup)
        
        if action == "lng":
            bot.answer_callback_query(call.id, f"Successfully claimed for {value}!")
        else:
            bot.answer_callback_query(call.id, "Status Updated!")

# --- STARTUP SEQUENCE ---
print("🤖 Clearing ghost instances...")
bot.remove_webhook()
print("🤖 Bot is running and listening for button clicks...")
bot.infinity_polling(skip_pending=True)
