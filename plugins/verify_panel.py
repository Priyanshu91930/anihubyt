# Verification Admin Panel - Manage verification system
# Created for AnihubFilter Bot

import logging
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from database.users_chats_db import db
from info import ADMINS
from utils import temp

logger = logging.getLogger(__name__)

# Temp storage for pending inputs
PENDING_INPUTS = {}

# ==================== VERIFY PANEL COMMAND ====================
# Using group=-1 to ensure this runs before other handlers
@Client.on_message(filters.command("verify_panel") & filters.private, group=-1)
async def verify_panel_cmd(client, message):
    """Admin command to open verification management panel"""
    user_id = message.from_user.id
    logger.info(f"verify_panel command received from user {user_id}")
    
    if user_id not in ADMINS:
        return await message.reply("⛔ This command is only for admins!")
    
    try:
        await send_verify_panel(client, message)
    except Exception as e:
        logger.error(f"Error in verify_panel: {e}")
        await message.reply(f"❌ Error: {e}")
    
    # Stop propagation to other handlers
    message.stop_propagation()


async def send_verify_panel(client, message, edit=False):
    """Send or edit the verification panel"""
    try:
        # Get current settings
        settings = await db.get_verify_settings()
        verified_count = await db.get_verified_users_count()
        
        status = "✅ ON" if settings.get('enabled', False) else "❌ OFF"
        shortlink_url = settings.get('shortlink_url', 'Not Set') or 'Not Set'
        shortlink_api = settings.get('shortlink_api', 'Not Set') or 'Not Set'
        validity_hours = settings.get('validity_hours', 24)
        
        # Mask API key for security
        if shortlink_api and shortlink_api != 'Not Set':
            masked_api = shortlink_api[:8] + "..." + shortlink_api[-4:] if len(shortlink_api) > 12 else "****"
        else:
            masked_api = 'Not Set'
        
        text = f"""<b>🔐 Verification Admin Panel</b>

━━━━━━━━━━━━━━━━━━━━

<b>📊 Status:</b> {status}
<b>👥 Verified Users:</b> {verified_count}
<b>⏰ Validity:</b> <code>{validity_hours} Hours</code>
<b>🔗 Shortlink URL:</b> <code>{shortlink_url}</code>
<b>🔑 Shortlink API:</b> <code>{masked_api}</code>

━━━━━━━━━━━━━━━━━━━━

<i>Use the buttons below to manage verification:</i>"""

        buttons = [
            [
                InlineKeyboardButton("✅ Turn ON" if not settings.get('enabled', False) else "❌ Turn OFF", 
                                   callback_data="vp_toggle")
            ],
            [
                InlineKeyboardButton("👥 View Users", callback_data="vp_users_0"),
                InlineKeyboardButton("⏰ Set Validity", callback_data="vp_validity")
            ],
            [
                InlineKeyboardButton("🔗 Set Shortlink", callback_data="vp_shortlink"),
                InlineKeyboardButton("🔑 Set API", callback_data="vp_api")
            ],
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="vp_refresh"),
                InlineKeyboardButton("❌ Close", callback_data="close_data")
            ]
        ]
        
        if edit:
            await message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)
        else:
            await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error sending verify panel: {e}")
        raise e


# ==================== TEXT INPUT HANDLER ====================
@Client.on_message(filters.private & filters.text & ~filters.command(["start", "help", "verify_panel"]), group=-1)
async def handle_verify_input(client, message):
    """Handle text input for verification settings"""
    user_id = message.from_user.id
    if user_id not in PENDING_INPUTS:
        return  # Let other handlers process this
    
    pending = PENDING_INPUTS.pop(user_id)
    input_type = pending.get('type')
    
    if message.text.lower() == "/cancel":
        await message.reply("❌ Cancelled!")
        message.stop_propagation()
        return
    
    try:
        settings = await db.get_verify_settings()
        
        if input_type == "shortlink_url":
            settings['shortlink_url'] = message.text.strip()
            await db.update_verify_settings(settings)
            await message.reply(f"✅ Shortlink URL set to: <code>{message.text.strip()}</code>", parse_mode=enums.ParseMode.HTML)
        
        elif input_type == "shortlink_api":
            settings['shortlink_api'] = message.text.strip()
            await db.update_verify_settings(settings)
            await message.reply("✅ Shortlink API key saved successfully!")
        
        elif input_type == "validity_hours":
            try:
                hours = int(message.text.strip())
                if hours < 1 or hours > 720:
                    await message.reply("❌ Please enter a number between 1 and 720 hours!")
                    return
                settings['validity_hours'] = hours
                await db.update_verify_settings(settings)
                await message.reply(f"✅ Verification validity set to <code>{hours} hours</code>!", parse_mode=enums.ParseMode.HTML)
            except ValueError:
                await message.reply("❌ Please enter a valid number!")
        
        message.stop_propagation()
    except Exception as e:
        logger.error(f"Error handling verify input: {e}")
        await message.reply(f"❌ Error: {e}")


# ==================== CALLBACK HANDLERS ====================
@Client.on_callback_query(filters.regex(r"^vp_"))
async def verify_panel_callback(client, query: CallbackQuery):
    """Handle verification panel callbacks"""
    if query.from_user.id not in ADMINS:
        return await query.answer("⛔ Only admins can use this!", show_alert=True)
    
    data = query.data
    
    try:
        # Toggle verification ON/OFF
        if data == "vp_toggle":
            settings = await db.get_verify_settings()
            new_status = not settings.get('enabled', False)
            settings['enabled'] = new_status
            await db.update_verify_settings(settings)
            
            status_text = "ON ✅" if new_status else "OFF ❌"
            await query.answer(f"Verification is now {status_text}", show_alert=True)
            await send_verify_panel(client, query.message, edit=True)
        
        # Refresh panel
        elif data == "vp_refresh":
            await send_verify_panel(client, query.message, edit=True)
            await query.answer("🔄 Refreshed!")
        
        # View verified users (with pagination)
        elif data.startswith("vp_users_"):
            page = int(data.split("_")[2])
            await show_verified_users(query, page)
        
        # Set shortlink URL prompt
        elif data == "vp_shortlink":
            PENDING_INPUTS[query.from_user.id] = {'type': 'shortlink_url'}
            text = """<b>🔗 Set Shortlink URL</b>

Send the shortlink domain (without https://)

<b>Example:</b> <code>atglinks.com</code>

Send /cancel to cancel."""
            
            await query.message.edit_text(text, parse_mode=enums.ParseMode.HTML)
            await query.answer("📝 Send the shortlink URL now...")
        
        # Set API key prompt
        elif data == "vp_api":
            PENDING_INPUTS[query.from_user.id] = {'type': 'shortlink_api'}
            text = """<b>🔑 Set Shortlink API Key</b>

Send your shortlink API key.

Send /cancel to cancel."""
            
            await query.message.edit_text(text, parse_mode=enums.ParseMode.HTML)
            await query.answer("📝 Send the API key now...")
        
        # Set validity hours
        elif data == "vp_validity":
            PENDING_INPUTS[query.from_user.id] = {'type': 'validity_hours'}
            text = """<b>⏰ Set Verification Validity</b>

Send the number of hours (e.g., 24, 48, 72)

Send /cancel to cancel."""
            
            await query.message.edit_text(text, parse_mode=enums.ParseMode.HTML)
            await query.answer("📝 Send the validity hours now...")
        
        # Revoke user verification
        elif data.startswith("vp_revoke_"):
            user_id = int(data.split("_")[2])
            await db.revoke_user_verification(user_id)
            await query.answer(f"✅ Revoked verification for user {user_id}", show_alert=True)
            await show_verified_users(query, 0)
        
        # Back to panel
        elif data == "vp_back":
            await send_verify_panel(client, query.message, edit=True)
    
    except Exception as e:
        logger.error(f"Error in verify callback: {e}")
        await query.answer(f"Error: {e}", show_alert=True)


async def show_verified_users(query, page):
    """Show verified users with pagination"""
    try:
        users_cursor = await db.get_all_verified_users()
        users = [user async for user in users_cursor]
        
        total_users = len(users)
        per_page = 10
        total_pages = (total_users + per_page - 1) // per_page if total_users > 0 else 1
        
        if total_users == 0:
            text = """<b>👥 Verified Users</b>

━━━━━━━━━━━━━━━━━━━━

<i>No verified users found.</i>

━━━━━━━━━━━━━━━━━━━━"""
            buttons = [[InlineKeyboardButton("⬅️ Back", callback_data="vp_back")]]
            await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)
            return
        
        # Get users for current page
        start_idx = page * per_page
        end_idx = start_idx + per_page
        page_users = users[start_idx:end_idx]
        
        text = f"""<b>👥 Verified Users ({total_users} total)</b>

━━━━━━━━━━━━━━━━━━━━

"""
        
        for i, user in enumerate(page_users, start=start_idx + 1):
            username = user.get('username', 'Unknown')
            user_id = user.get('user_id', 'Unknown')
            text += f"<b>{i}.</b> @{username} | <code>{user_id}</code>\n"
        
        text += f"""
━━━━━━━━━━━━━━━━━━━━

<i>Page {page + 1}/{total_pages}</i>"""

        buttons = []
        
        # Add user revoke buttons (2 per row)
        row = []
        for user in page_users:
            user_id = user.get('user_id')
            username = user.get('username', str(user_id))[:15]
            row.append(InlineKeyboardButton(f"❌ {username}", callback_data=f"vp_revoke_{user_id}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        
        # Navigation buttons
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"vp_users_{page - 1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"vp_users_{page + 1}"))
        if nav_buttons:
            buttons.append(nav_buttons)
        
        buttons.append([InlineKeyboardButton("⬅️ Back to Panel", callback_data="vp_back")])
        
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error showing verified users: {e}")
        await query.answer(f"Error: {e}", show_alert=True)
