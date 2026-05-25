import os
import time
import threading
import urllib.parse
import base64
from datetime import datetime, timezone
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from supabase import create_client, Client

# --- CONFIG ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_GROUP_ID = os.getenv("TELEGRAM_GROUP_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
#      MEMORY TRACKERS (Reminders & Live Receipts)
# ==========================================
reminders_tracker = {}
group_msg_tracker = {} # Tracks the group message ID to update it live from DMs!

# --- KEYBOARD GENERATOR ---
def generate_guest_keyboard(guest, page="main"):
    markup = InlineKeyboardMarkup(row_width=3)
    g_id = guest['id']
    lounge = str(guest.get('lounge', ''))
    
    # STATE: Unassigned or Pending Reassignment (Shows Dispatch Buttons)
    if not lounge or lounge == 'Unassigned' or lounge.startswith('Pending'):
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
        
        markup.add(InlineKeyboardButton("⚙️ More Options", callback_data=f"pag:{g_id}:opt"))
        markup.add(InlineKeyboardButton("🏁 Complete Visit", callback_data=f"cmp:{g_id}:done"))

    # --- MORE OPTIONS PAGE ---
    elif page == "opt":
        markup.add(
            InlineKeyboardButton("📸 Add/Update Photo", callback_data=f"pag:{g_id}:pho"),
            InlineKeyboardButton("🔄 Transfer Lounge", callback_data=f"pag:{g_id}:trn")
        )
        
        wa_msg = (
            f"*{lounge}*\n"
            f"{guest.get('guest_name', '')}\n"
            f"📺 LMW: {guest.get('lmw_status', 'Not yet')}\n"
            f"💻 IP Demo: {guest.get('demo_status', 'Not yet')}\n"
            f"⏳ Ready for Vyas: {'✅' if guest.get('ready_to_meet_gurudev') else '❌'}\n"
            f"🤝 Met Gurudev: {'✅' if guest.get('met_gurudev') else '❌'}"
        )
        wa_url = f"https://wa.me/?text={urllib.parse.quote(wa_msg)}"
        markup.add(InlineKeyboardButton("📲 WhatsApp", url=wa_url))
        
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
    lounge = str(guest.get('lounge', ''))
    
    if not lounge or lounge == 'Unassigned':
        return f"🚨 *New Arrival*\n👤 *{guest['guest_name']}*\n📍 Lounge: *Unassigned*\n\n👇 *Please claim and assign a lounge:*"
        
    if lounge.startswith('Pending'):
        target = lounge.replace('Pending ', '')
        return f"🚨 *Room Reassignment!*\n👤 *{guest['guest_name']}*\n👉 Transferring to: *{target}*\n\n👇 *New team member, please claim below:*"
    
    text = f"*{lounge}*\n"
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

# --- LIVE GROUP RECEIPT SYNKER ---
def update_group_live_receipt(g_id, guest, user_name):
    if g_id in group_msg_tracker and TELEGRAM_GROUP_ID:
        msg_info = group_msg_tracker[g_id]
        
        if guest.get('jai_gurudev'):
            text = f"🏁 *{guest['guest_name']} - Visit Complete*\n_Finalized by @{user_name}_"
        else:
            text = f"*{guest.get('lounge', 'Unassigned')}*\n"
            text += f"👤 *{guest['guest_name']}*\n\n"
            text += f"📺 LMW: {guest.get('lmw_status', 'Not yet')}\n"
            text += f"💻 IP Demo: {guest.get('demo_status', 'Not yet')}\n"
            text += f"⏳ Ready for Vyas: {'✅' if guest.get('ready_to_meet_gurudev') else '❌'}\n"
            text += f"🤝 Met Gurudev: {'✅' if guest.get('met_gurudev') else '❌'}\n\n"
            text += f"_🔒 Managed in DMs by @{user_name}_"
            
        try:
            if msg_info['is_photo']:
                bot.edit_message_caption(caption=text, chat_id=TELEGRAM_GROUP_ID, message_id=msg_info['msg_id'], parse_mode="Markdown", reply_markup=None)
            else:
                bot.edit_message_text(text=text, chat_id=TELEGRAM_GROUP_ID, message_id=msg_info['msg_id'], parse_mode="Markdown", reply_markup=None)
        except Exception:
            pass 

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

# ==========================================
#      SMART BACKGROUND REMINDER LOOP
# ==========================================
def reminder_loop():
    while True:
        time.sleep(60) 
        try:
            res = supabase.table("guests").select("*").eq("is_active", True).eq("jai_gurudev", False).execute()
            active_guests = res.data
            
            current_time = time.time()
            active_unassigned_ids = set()
            
            for guest in active_guests:
                lounge = str(guest.get('lounge', ''))
                if not lounge or lounge == 'Unassigned' or lounge.startswith('Pending'):
                    g_id = guest['id']
                    active_unassigned_ids.add(g_id)
                    
                    if g_id not in reminders_tracker:
                        # Start tracking the guest
                        reminders_tracker[g_id] = {'last_time': current_time, 'msg_id': None}
                    else:
                        if current_time - reminders_tracker[g_id]['last_time'] >= 180:
                            
                            # 1. 🧹 DELETE THE OLD REMINDER!
                            old_msg_id = reminders_tracker[g_id].get('msg_id')
                            if old_msg_id and TELEGRAM_GROUP_ID:
                                try:
                                    bot.delete_message(TELEGRAM_GROUP_ID, old_msg_id)
                                except Exception:
                                    pass
                            
                            # 2. 🧮 CALCULATE TOTAL WAIT TIME
                            minutes_waiting = "3+"
                            try:
                                created_str = guest.get('created_at', '')
                                if created_str:
                                    # Handle Supabase ISO timestamp format
                                    created_str = created_str.replace('Z', '+00:00')
                                    created_time = datetime.fromisoformat(created_str)
                                    now = datetime.now(timezone.utc)
                                    delta = now - created_time
                                    minutes_waiting = int(delta.total_seconds() / 60)
                            except Exception:
                                pass # Fails safely back to "3+" if parsing fails

                            # 3. 📸 SEND THE NEW REMINDER (WITH DYNAMIC TIME & PHOTO)
                            if TELEGRAM_GROUP_ID:
                                base_text = generate_guest_text(guest)
                                reminder_text = f"⏰ *REMINDER: WAITING {minutes_waiting} MINS!*\n\n{base_text}"
                                markup = generate_guest_keyboard(guest, page="main")
                                
                                new_msg_id = None
                                try:
                                    if guest.get('photo_data'):
                                        # Decode the raw photo from Supabase
                                        img_bytes = base64.b64decode(guest['photo_data'])
                                        sent_msg = bot.send_photo(
                                            chat_id=TELEGRAM_GROUP_ID, 
                                            photo=img_bytes, 
                                            caption=reminder_text, 
                                            reply_markup=markup, 
                                            parse_mode="Markdown"
                                        )
                                        new_msg_id = sent_msg.message_id
                                    else:
                                        sent_msg = bot.send_message(
                                            chat_id=TELEGRAM_GROUP_ID, 
                                            text=reminder_text, 
                                            reply_markup=markup, 
                                            parse_mode="Markdown"
                                        )
                                        new_msg_id = sent_msg.message_id
                                except Exception as e:
                                    pass
                                    
                                # Reset the clock & save the new message ID so it can be deleted next time
                                reminders_tracker[g_id]['last_time'] = current_time
                                reminders_tracker[g_id]['msg_id'] = new_msg_id
            
            # 🧹 Cleanup abandoned guests
            for g_id in list(reminders_tracker.keys()):
                if g_id not in active_unassigned_ids:
                    # If they were claimed via Streamlit Manager, wipe the floating reminder!
                    old_msg_id = reminders_tracker[g_id].get('msg_id')
                    if old_msg_id and TELEGRAM_GROUP_ID:
                        try:
                            bot.delete_message(TELEGRAM_GROUP_ID, old_msg_id)
                        except Exception:
                            pass
                    del reminders_tracker[g_id]
                    
        except Exception as e:
            pass 

threading.Thread(target=reminder_loop, daemon=True).start()

# --- CALLBACK HANDLER ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    action, g_id, value = call.data.split(':')
    user_name = call.from_user.username or call.from_user.first_name
    
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
    lounge = str(guest.get('lounge', ''))
    if action == "lng" and lounge and lounge != "Unassigned" and not lounge.startswith('Pending'):
        bot.answer_callback_query(call.id, "⚠️ Too late! Already claimed.", show_alert=True)
        new_text = generate_guest_text(guest)
        new_markup = generate_guest_keyboard(guest)
        update_tg_message(call, new_text, new_markup)
        return

    # Determine Update Payload
    update_data = {}
    if action == "lng": update_data = {"lounge": value} 
    elif action == "trn": update_data = {"lounge": f"Pending {value}"} 
    elif action == "lmw": update_data = {"lmw_status": value}
    elif action == "dmo": update_data = {"demo_status": value}
    elif action == "rdy": update_data = {"ready_to_meet_gurudev": not guest.get('ready_to_meet_gurudev', False)}
    elif action == "gur": update_data = {"met_gurudev": not guest.get('met_gurudev', False)}
    elif action == "cmp": update_data = {"jai_gurudev": True}

    # Update Supabase
    updated_res = supabase.table("guests").update(update_data).eq("id", g_id).execute()
    updated_guest = updated_res.data[0]

    if action == "cmp":
        final_text = f"🏁 *{updated_guest['guest_name']} - Visit Complete*\n_Finalized by @{user_name}_"
        update_tg_message(call, final_text, None)
        
        update_group_live_receipt(g_id, updated_guest, user_name)
        if g_id in group_msg_tracker: del group_msg_tracker[g_id]
        
        try: bot.answer_callback_query(call.id, "Visit Completed!")
        except: pass
        
    elif action == "trn":
        dm_receipt = f"🔄 *Transfer Initiated*\n👤 *{updated_guest['guest_name']}*\n_This guest was sent back to the group for reassignment to {value}._"
        update_tg_message(call, dm_receipt, None)
        
        if g_id in group_msg_tracker and TELEGRAM_GROUP_ID:
            try: bot.delete_message(TELEGRAM_GROUP_ID, group_msg_tracker[g_id]['msg_id'])
            except: pass
            del group_msg_tracker[g_id]
        
        if TELEGRAM_GROUP_ID:
            new_text = generate_guest_text(updated_guest)
            new_markup = generate_guest_keyboard(updated_guest, page="main")
            try:
                if call.message.content_type == 'photo':
                    sent_msg = bot.send_photo(chat_id=TELEGRAM_GROUP_ID, photo=call.message.photo[-1].file_id, caption=new_text, reply_markup=new_markup, parse_mode="Markdown")
                else:
                    sent_msg = bot.send_message(chat_id=TELEGRAM_GROUP_ID, text=new_text, reply_markup=new_markup, parse_mode="Markdown")
                
                # ⚡️ Save this Reassignment message to the reminder tracker, so the loop can delete it when a reminder triggers!
                reminders_tracker[g_id] = {'last_time': time.time(), 'msg_id': sent_msg.message_id}
            except Exception:
                pass
                
        try: bot.answer_callback_query(call.id, f"Transferred to {value}!")
        except: pass

    elif action == "lng":
        # ⚡️ CLEANUP CHECK: If they claim the guest, delete any floating reminder message!
        if g_id in reminders_tracker:
            reminder_msg_id = reminders_tracker[g_id].get('msg_id')
            if reminder_msg_id and reminder_msg_id != call.message.message_id:
                if TELEGRAM_GROUP_ID:
                    try: bot.delete_message(TELEGRAM_GROUP_ID, reminder_msg_id)
                    except: pass
            reminders_tracker[g_id]['msg_id'] = None

        # --- THE DM FORK ---
        dm_text = generate_guest_text(updated_guest, updated_by=user_name)
        dm_markup = generate_guest_keyboard(updated_guest, page="main")
        
        try:
            if call.message.content_type == 'photo':
                bot.send_photo(call.from_user.id, photo=call.message.photo[-1].file_id, caption=dm_text, reply_markup=dm_markup, parse_mode="Markdown")
            else:
                bot.send_message(call.from_user.id, dm_text, reply_markup=dm_markup, parse_mode="Markdown")
        except Exception:
            bot.answer_callback_query(call.id, "⚠️ ERROR: You must message the bot directly and click /start before claiming!", show_alert=True)
            supabase.table("guests").update({"lounge": "Unassigned"}).eq("id", g_id).execute()
            return
            
        # ⚡️ LOCK THE GROUP MESSAGE & SYNC IT LIVE
        group_msg_tracker[g_id] = {
            "msg_id": call.message.message_id,
            "is_photo": call.message.content_type == 'photo'
        }
        update_group_live_receipt(g_id, updated_guest, user_name)
        
        bot.answer_callback_query(call.id, "Check your DMs to manage this guest!")
        
    else:
        # --- NORMAL UPDATES (Inside the DM) ---
        new_text = generate_guest_text(updated_guest, updated_by=user_name)
        new_markup = generate_guest_keyboard(updated_guest, page="main") 
        update_tg_message(call, new_text, new_markup)
        update_group_live_receipt(g_id, updated_guest, user_name)

print("🤖 Bot is running and listening for button clicks...")
bot.infinity_polling(skip_pending=True)