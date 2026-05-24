import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from supabase import create_client, Client

# --- CONFIG ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- KEYBOARD GENERATOR (With Pagination) ---
def generate_guest_keyboard(guest, page="main"):
    markup = InlineKeyboardMarkup(row_width=3)
    g_id = guest['id']
    
    # Unassigned State
    if not guest.get('lounge') or guest.get('lounge') == 'Unassigned':
        markup.add(
            InlineKeyboardButton("L1", callback_data=f"lng:{g_id}:L1"),
            InlineKeyboardButton("L2", callback_data=f"lng:{g_id}:L2"),
            InlineKeyboardButton("L3", callback_data=f"lng:{g_id}:L3"),
            InlineKeyboardButton("BR", callback_data=f"lng:{g_id}:BR"),
            InlineKeyboardButton("L5", callback_data=f"lng:{g_id}:L5")
        )
        return markup

    # --- MAIN WORKFLOW PAGE ---
    if page == "main":
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
        
        # More Options Button
        markup.add(InlineKeyboardButton("⚙️ More Options", callback_data=f"pag:{g_id}:opt"))
        markup.add(InlineKeyboardButton("🏁 Complete Visit", callback_data=f"cmp:{g_id}:done"))

    # --- MORE OPTIONS PAGE ---
    elif page == "opt":
        markup.add(
            InlineKeyboardButton("📸 Add/Update Photo", callback_data=f"pag:{g_id}:pho"),
            InlineKeyboardButton("🔄 Transfer Lounge", callback_data=f"pag:{g_id}:trn")
        )
        markup.add(InlineKeyboardButton("🔙 Back", callback_data=f"pag:{g_id}:main"))

    # --- TRANSFER LOUNGE PAGE ---
    elif page == "trn":
        markup.add(
            InlineKeyboardButton("L1", callback_data=f"trn:{g_id}:L1"),
            InlineKeyboardButton("L2", callback_data=f"trn:{g_id}:L2"),
            InlineKeyboardButton("L3", callback_data=f"trn:{g_id}:L3"),
            InlineKeyboardButton("BR", callback_data=f"trn:{g_id}:BR"),
            InlineKeyboardButton("L5", callback_data=f"trn:{g_id}:L5")
        )
        markup.add(InlineKeyboardButton("🔙 Cancel Transfer", callback_data=f"pag:{g_id}:opt"))

    return markup

# --- MESSAGE TEXT GENERATOR ---
def generate_guest_text(guest, updated_by=None):
    if not guest.get('lounge') or guest.get('lounge') == 'Unassigned':
        return f"🚨 *New Arrival*\n👤 *{guest['guest_name']}*\n📍 Lounge: *Unassigned*\n\n👇 *Please claim and assign a lounge:*"
    
    # Clean Title Update
    text = f"*{guest.get('lounge')}*\n"
    text += f"👤 *{guest['guest_name']}*\n\n"
    text += f"📺 LMW: {guest.get('lmw_status', 'Not yet')}\n"
    text += f"💻 IP Demo: {guest.get('demo_status', 'Not yet')}\n"
    text += f"⏳ Ready for Vyas: {'✅' if guest.get('ready_to_meet_gurudev') else '❌'}\n"
    text += f"🤝 Met Gurudev: {'✅' if guest.get('met_gurudev') else '❌'}\n"
    
    if updated_by:
        text += f"\n_Last updated by @{updated_by}_"
        
    return text

# --- SMART EDIT HELPER ---
def update_tg_message(call, new_text, new_markup):
    if call.message.content_type == 'text':
        bot.edit_message_text(text=new_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=new_markup)
    else:
        bot.edit_message_caption(caption=new_text, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=new_markup)

# ==========================================
#      PHOTO REPLY HANDLER
# ==========================================
@bot.message_handler(content_types=['photo'])
def handle_photo_reply(message):
    if not message.reply_to_message or not message.reply_to_message.text:
        return
        
    if "[Ref:" in message.reply_to_message.text:
        try:
            ref_data = message.reply_to_message.text.split("[Ref: ")[1].split("]")[0]
            g_id, orig_msg_id = ref_data.split("|")
            orig_msg_id = int(orig_msg_id)
        except Exception as e:
            return
            
        res = supabase.table("guests").select("*").eq("id", g_id).execute()
        if not res.data:
            return
        guest = res.data[0]
        
        photo_id = message.photo[-1].file_id
        new_text = generate_guest_text(guest)
        new_markup = generate_guest_keyboard(guest, page="main")
        
        bot.send_photo(
            chat_id=message.chat.id,
            photo=photo_id,
            caption=new_text,
            parse_mode="Markdown",
            reply_markup=new_markup
        )
        
        try:
            bot.delete_message(message.chat.id, orig_msg_id) 
            bot.delete_message(message.chat.id, message.reply_to_message.message_id) 
            bot.delete_message(message.chat.id, message.message_id) 
        except:
            pass 

# --- CALLBACK HANDLER ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    action, g_id, value = call.data.split(':')
    user_name = call.from_user.username or call.from_user.first_name
    
    # ⚡️ SPEED FIX: Instantly kill the Telegram loading spinner
    if action != "lng" and action != "pag":
        try: bot.answer_callback_query(call.id)
        except: pass

    res = supabase.table("guests").select("*").eq("id", g_id).execute()
    if not res.data:
        try: bot.answer_callback_query(call.id, "Guest not found in database.", show_alert=True)
        except: pass
        return
    guest = res.data[0]

    # --- SUB-MENU NAVIGATION ---
    if action == "pag":
        if value == "pho":
            prompt_text = f"📸 **Please reply directly to this message** with a photo for {guest['guest_name']}.\n\n`[Ref: {g_id}|{call.message.message_id}]`"
            bot.send_message(call.message.chat.id, prompt_text, parse_mode="Markdown")
            bot.answer_callback_query(call.id, "Please reply to the new message with the photo!")
        else:
            new_text = generate_guest_text(guest, updated_by=user_name)
            new_markup = generate_guest_keyboard(guest, page=value)
            update_tg_message(call, new_text, new_markup)
            bot.answer_callback_query(call.id)
        return

    # Race condition check for initial assignment
    if action == "lng" and guest.get('lounge') and guest.get('lounge') != "Unassigned":
        bot.answer_callback_query(call.id, "⚠️ Too late! Already claimed.", show_alert=True)
        new_text = generate_guest_text(guest)
        new_markup = generate_guest_keyboard(guest)
        update_tg_message(call, new_text, new_markup)
        return

    # Determine Update Payload
    update_data = {}
    if action == "lng" or action == "trn": update_data = {"lounge": value} 
    elif action == "lmw": update_data = {"lmw_status": value}
    elif action == "dmo": update_data = {"demo_status": value}
    elif action == "rdy": update_data = {"ready_to_meet_gurudev": not guest.get('ready_to_meet_gurudev', False)}
    elif action == "gur": update_data = {"met_gurudev": not guest.get('met_gurudev', False)}
    elif action == "cmp": update_data = {"jai_gurudev": True}

    # Update Supabase
    updated_res = supabase.table("guests").update(update_data).eq("id", g_id).execute()
    updated_guest = updated_res.data[0]

    # Update Telegram Message In-Place
    if action == "cmp":
        final_text = f"🏁 *{updated_guest['guest_name']} - Visit Complete*\n_Finalized by @{user_name}_"
        update_tg_message(call, final_text, None)
        try: bot.answer_callback_query(call.id, "Visit Completed!")
        except: pass
        
    elif action == "lng":
        # --- THE DM FORK (When a lounge is claimed) ---
        dm_text = generate_guest_text(updated_guest, updated_by=user_name)
        dm_markup = generate_guest_keyboard(updated_guest, page="main")
        
        try:
            bot.send_message(call.from_user.id, dm_text, reply_markup=dm_markup, parse_mode="Markdown")
        except Exception:
            bot.answer_callback_query(call.id, "⚠️ ERROR: You must message the bot directly and click /start before claiming!", show_alert=True)
            supabase.table("guests").update({"lounge": "Unassigned"}).eq("id", g_id).execute()
            return
            
        group_receipt = f"*{value}*\n👤 *{updated_guest['guest_name']}*\n\n_Management moved to DMs by @{user_name}_"
        update_tg_message(call, group_receipt, None)
        bot.answer_callback_query(call.id, "Check your DMs to manage this guest!")
        
    else:
        # --- NORMAL UPDATES ---
        new_text = generate_guest_text(updated_guest, updated_by=user_name)
        new_markup = generate_guest_keyboard(updated_guest, page="main") 
        update_tg_message(call, new_text, new_markup)

print("🤖 Bot is running and listening for button clicks...")
bot.infinity_polling(skip_pending=True)