# safe_repo

from pyrogram import filters, Client
from pyrogram.enums import ParseMode, ChatType
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from safe_repo import app
from safe_repo.core.mongo import db
from safe_repo.core.func import subscribe, chk_user
from pyrogram.errors import (
    ApiIdInvalid,
    PhoneNumberInvalid,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    SessionPasswordNeeded,
    PasswordHashInvalid,
    FloodWait
)
import random
import os
import string
import asyncio
from asyncio.exceptions import TimeoutError

# Constants for timeouts
TIMEOUT_OTP = 600  # 10 minutes
TIMEOUT_2FA = 300  # 5 minutes

session_data = {}

def generate_random_name(length=7):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

async def delete_session_files(user_id):
    session_file = f"session_{user_id}.session"
    memory_file = f"session_{user_id}.session-journal"

    session_file_exists = os.path.exists(session_file)
    memory_file_exists = os.path.exists(memory_file)

    if session_file_exists:
        os.remove(session_file)
    
    if memory_file_exists:
        os.remove(memory_file)

    # Delete session from the database
    if session_file_exists or memory_file_exists:
        await db.delete_session(user_id)
        return True  # Files were deleted
    return False  # No files found

@app.on_message(filters.command("logout"))
async def clear_db(client, message):
    user_id = message.chat.id
    files_deleted = await delete_session_files(user_id)

    if files_deleted:
        await message.reply("✅ Your session data and files have been cleared from memory and disk.")
    else:
        await message.reply("⚠️ You are not logged in, no session data found.")

@app.on_message(filters.command("login"))
async def generate_session(client, message):
    joined = await subscribe(client, message)
    if joined == 1:
        return

    user_id = message.chat.id

    # Initialize session data
    session_data[user_id] = {"type": "Pyrogram"}
    
    # Send welcome message and start button
    await client.send_message(
        chat_id=user_id,
        text=(
            "**💥 Welcome to the Pyrogram session setup!**\n"
            "**━━━━━━━━━━━━━━━━━**\n"
            "**This is a totally safe session string generator. We don't save any info that you will provide, so this is completely safe.**\n\n"
            "**Note: Don't send OTP directly. Otherwise, your account could be banned, or you may not be able to log in.**"
        ),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Start", callback_data="session_start_pyrogram"),
            InlineKeyboardButton("Close", callback_data="session_close")
        ]]),
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query(filters.regex(r"^session_start_|^session_restart_|^session_close$"))
async def callback_query_handler(client, callback_query):
    data = callback_query.data
    chat_id = callback_query.message.chat.id

    if data == "session_close":
        await callback_query.message.edit_text(
            "**❌ Cancelled. You can start by sending /login**",
            parse_mode=ParseMode.MARKDOWN
        )
        if chat_id in session_data:
            del session_data[chat_id]
        return

    if data.startswith("session_start_") or data.startswith("session_restart_"):
        session_type = "pyrogram"
        await callback_query.message.edit_text(
            "**Send Your API ID**",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Restart", callback_data=f"session_restart_{session_type}"),
                InlineKeyboardButton("Close", callback_data="session_close")
            ]]),
            parse_mode=ParseMode.MARKDOWN
        )
        session_data[chat_id]["stage"] = "api_id"

@app.on_message(filters.text & filters.create(lambda _, __, message: message.chat.id in session_data))
async def text_handler(client, message: Message):
    chat_id = message.chat.id
    if chat_id not in session_data:
        return

    session = session_data[chat_id]
    stage = session.get("stage")

    if stage == "api_id":
        try:
            api_id = int(message.text)
            session["api_id"] = api_id
            await client.send_message(
                chat_id=chat_id,
                text="**Send Your API Hash**",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Restart", callback_data=f"session_restart_{session['type'].lower()}"),
                    InlineKeyboardButton("Close", callback_data="session_close")
                ]]),
                parse_mode=ParseMode.MARKDOWN
            )
            session["stage"] = "api_hash"
        except ValueError:
            await client.send_message(
                chat_id=chat_id,
                text="**❌ Invalid API ID. Please enter a valid integer.**"
            )

    elif stage == "api_hash":
        session["api_hash"] = message.text
        await client.send_message(
            chat_id=chat_id,
            text="**Send Your Phone Number\n[Example: +880xxxxxxxxxx]**",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Restart", callback_data=f"session_restart_{session['type'].lower()}"),
                InlineKeyboardButton("Close", callback_data="session_close")
            ]]),
            parse_mode=ParseMode.MARKDOWN
        )
        session["stage"] = "phone_number"

    elif stage == "phone_number":
        session["phone_number"] = message.text
        otp_message = await client.send_message(
            chat_id=chat_id,
            text="**💥 Sending OTP...**"
        )
        await send_otp(client, message, otp_message)

    elif stage == "otp":
        otp = ''.join([char for char in message.text if char.isdigit()])
        session["otp"] = otp
        otp_message = await client.send_message(
            chat_id=chat_id,
            text="**💥 Validating Your Inputted OTP...**"
        )
        await validate_otp(client, message, otp_message)

    elif stage == "2fa":
        session["password"] = message.text
        await validate_2fa(client, message)

async def send_otp(client, message, otp_message):
    session = session_data[message.chat.id]
    api_id = session["api_id"]
    api_hash = session["api_hash"]
    phone_number = session["phone_number"]
    user_id = message.chat.id

    try:
        client_obj = Client(f"session_{user_id}", api_id, api_hash)
        await client_obj.connect()
        code = await client_obj.send_code(phone_number)
        session["client_obj"] = client_obj
        session["code"] = code
        session["stage"] = "otp"

        # Start a timeout task for OTP expiry
        asyncio.create_task(handle_otp_timeout(client, message))

        await client.send_message(
            chat_id=message.chat.id,
            text="**✅ Send The OTP as text. Please send a text message embedding the OTP like: '12345'**",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Restart", callback_data=f"session_restart_{session['type'].lower()}"),
                InlineKeyboardButton("Close", callback_data="session_close")
            ]]),
            parse_mode=ParseMode.MARKDOWN
        )
        await otp_message.delete()
    except ApiIdInvalid:
        await client.send_message(
            chat_id=message.chat.id,
            text='**❌ `API_ID` and `API_HASH` combination is invalid**',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Restart", callback_data=f"session_restart_{session['type'].lower()}"),
                InlineKeyboardButton("Close", callback_data="session_close")
            ]])
        )
        await otp_message.delete()
        return
    except PhoneNumberInvalid:
        await client.send_message(
            chat_id=message.chat.id,
            text='**❌ `PHONE_NUMBER` is invalid.**',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Restart", callback_data=f"session_restart_{session['type'].lower()}"),
                InlineKeyboardButton("Close", callback_data="session_close")
            ]])
        )
        await otp_message.delete()
        return
    except FloodWait as e:
        await client.send_message(
            chat_id=message.chat.id,
            text=f'**❌ Flood wait error. Please try again after {e.x} seconds.**',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Restart", callback_data=f"session_restart_{session['type'].lower()}"),
                InlineKeyboardButton("Close", callback_data="session_close")
            ]])
        )
        await otp_message.delete()
        return
    except Exception as e:
        await client.send_message(
            chat_id=message.chat.id,
            text=f'**❌ Failed to send OTP: {e}. Please try again later.**',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Restart", callback_data=f"session_restart_{session['type'].lower()}"),
                InlineKeyboardButton("Close", callback_data="session_close")
            ]])
        )
        await otp_message.delete()
        return

async def handle_otp_timeout(client, message):
    await asyncio.sleep(TIMEOUT_OTP)
    if message.chat.id in session_data and session_data[message.chat.id].get("stage") == "otp":
        await client.send_message(
            chat_id=message.chat.id,
            text="**❌ Your OTP has expired**",
            parse_mode=ParseMode.MARKDOWN
        )
        del session_data[message.chat.id]

async def validate_otp(client, message, otp_message):
    session = session_data[message.chat.id]
    client_obj = session["client_obj"]
    phone_number = session["phone_number"]
    otp = session["otp"]
    code = session["code"]

    try:
        await client_obj.sign_in(phone_number, code.phone_code_hash, otp)
        await generate_session(client, message)
        await otp_message.delete()
    except PhoneCodeInvalid:
        await client.send_message(
            chat_id=message.chat.id,
            text='**❌ Your OTP is wrong**',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Restart", callback_data=f"session_restart_{session['type'].lower()}"),
                InlineKeyboardButton("Close", callback_data="session_close")
            ]])
        )
        await otp_message.delete()
        return
    except PhoneCodeExpired:
        await client.send_message(
            chat_id=message.chat.id,
            text='**❌ OTP has expired**',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Restart", callback_data=f"session_restart_{session['type'].lower()}"),
                InlineKeyboardButton("Close", callback_data="session_close")
            ]])
        )
        await otp_message.delete()
        return
    except SessionPasswordNeeded:
        session["stage"] = "2fa"
        asyncio.create_task(handle_2fa_timeout(client, message))
        await client.send_message(
            chat_id=message.chat.id,
            text="**❌ 2FA is required to login. Please enter 2FA password**",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Restart", callback_data=f"session_restart_{session['type'].lower()}"),
                InlineKeyboardButton("Close", callback_data="session_close")
            ]]),
            parse_mode=ParseMode.MARKDOWN
        )
        await otp_message.delete()

async def handle_2fa_timeout(client, message):
    await asyncio.sleep(TIMEOUT_2FA)
    if message.chat.id in session_data and session_data[message.chat.id].get("stage") == "2fa":
        await client.send_message(
            chat_id=message.chat.id,
            text="**❌ Your 2FA input has expired**",
            parse_mode=ParseMode.MARKDOWN
        )
        del session_data[message.chat.id]

async def validate_2fa(client, message):
    session = session_data[message.chat.id]
    client_obj = session["client_obj"]
    password = session["password"]

    try:
        await client_obj.check_password(password=password)
        await generate_session(client, message)
    except PasswordHashInvalid:
        await client.send_message(
            chat_id=message.chat.id,
            text='**❌ Invalid Password Provided**',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Restart", callback_data=f"session_restart_{session['type'].lower()}"),
                InlineKeyboardButton("Close", callback_data="session_close")
            ]])
        )
        return

async def generate_session(client, message):
    session = session_data[message.chat.id]
    client_obj = session["client_obj"]
    user_id = message.chat.id

    string_session = await client_obj.export_session_string()
    await db.set_session(user_id, string_session)
    await client_obj.disconnect()

    await client.send_message(
        chat_id=message.chat.id,
        text="**✅ Login successful! Your session has been saved.**",
        parse_mode=ParseMode.MARKDOWN
    )
    del session_data[message.chat.id]
