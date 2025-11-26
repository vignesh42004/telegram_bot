if __name__ == "__main__":
    exit("Run bot.py instead!")

import logging
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from database import db
from helpers import (
    check_subscription,
    get_movie_info,
    get_short_link,
    encode_payload,
    decode_payload,
    normalize_name
)

logger = logging.getLogger(__name__)


def register_user_handlers(app: Client):
    
    # ============ /start COMMAND ============
    @app.on_message(filters.command("start") & filters.private)
    async def start_cmd(bot: Client, message: Message):
        user_id = message.from_user.id
        username = message.from_user.username
        text = message.text.strip()
        
        logger.info(f"START from {user_id}: {text}")
        
        # Save user
        await db.add_user(user_id, username)
        
        # Get payload
        parts = text.split(maxsplit=1)
        
        # No payload - show welcome
        if len(parts) == 1:
            await send_welcome(message)
            return
        
        payload = parts[1].strip()
        
        # Empty payload
        if not payload:
            await send_welcome(message)
            return
        
        # Block controller payloads
        blocked = ["connect", "controller", "setup", "config", "admin", "panel", "settings"]
        if any(b in payload.lower() for b in blocked):
            if user_id != Config.ADMIN_ID:
                await send_welcome(message)
                return
        
        # Decode payload
        movie_code, part, token = decode_payload(payload)
        
        logger.info(f"Decoded: code={movie_code}, part={part}, token={token[:10] if token else 'None'}...")
        
        # Invalid payload
        if not movie_code:
            await send_welcome(message)
            return
        
        # Check subscription
        if not await check_subscription(bot, user_id):
            await message.reply_text(
                "🔒 **Join to Continue**\n\n"
                "You must join our channel first.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Join Channel", url=Config.BACKUP_CHANNEL_LINK)],
                    [InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{bot.me.username}?start={payload}")]
                ]),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Has token - send file
        if token:
            token_data = await db.verify_token(token, user_id)
            
            if token_data:
                movie = await db.get_movie(token_data["movie_code"])
                
                if movie:
                    part_idx = token_data.get("part", 1) - 1
                    file_ids = movie.get("file_ids", [])
                    
                    if 0 <= part_idx < len(file_ids) and file_ids[part_idx]:
                        try:
                            await bot.send_cached_media(
                                chat_id=user_id,
                                file_id=file_ids[part_idx],
                                caption=f"🎬 **{movie['title']}**\n\n✅ Enjoy!",
                                parse_mode=ParseMode.MARKDOWN
                            )
                        except:
                            await message.reply_document(
                                file_ids[part_idx],
                                caption=f"🎬 **{movie['title']}**",
                                parse_mode=ParseMode.MARKDOWN
                            )
                        return
                
                await message.reply_text("❌ File not available. Try searching again.")
                return
            
            await message.reply_text("⏰ Link expired! Please search again.")
            return
        
        # No token - get movie
        movie = await db.get_movie(movie_code)
        
        if not movie:
            await send_welcome(message)
            return
        
        # Multi-part
        if movie.get("parts", 1) > 1:
            buttons = []
            for i in range(1, movie["parts"] + 1):
                buttons.append(InlineKeyboardButton(f"📦 Part {i}", callback_data=f"part:{movie_code}:{i}"))
            
            keyboard = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
            
            await message.reply_text(
                f"🎬 **{movie['title']}**\n\n"
                f"This movie has {movie['parts']} parts.\n"
                f"Select one:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Single part - generate link
        new_token = await db.create_token(user_id, movie_code, part)
        final_payload = encode_payload(movie_code, part, new_token)
        final_link = f"https://t.me/{bot.me.username}?start={final_payload}"
        
        status = await message.reply_text("🔄 Generating link...")
        
        short_link = await get_short_link(final_link)
        
        await status.edit_text(
            f"✅ **{movie['title']}**\n\n"
            f"Click below to download:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔓 Download", url=short_link)]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )
    
    
    # ============ /help COMMAND ============
    @app.on_message(filters.command("help") & filters.private)
    async def help_cmd(bot: Client, message: Message):
        user_id = message.from_user.id
        
        text = (
            "🎬 **Movie Bot**\n\n"
            "Send movie name to search.\n\n"
            "**Examples:**\n"
            "• Dune\n"
            "• Avengers\n"
            "• Interstellar"
        )
        
        if user_id == Config.ADMIN_ID:
            text += (
                "\n\n**Admin:**\n"
                "`/add` `/addpart` `/delete`\n"
                "`/list` `/stats` `/broadcast`"
            )
        
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    
    
    # ============ SEARCH (any text) ============
    @app.on_message(filters.text & filters.private)
    async def search_cmd(bot: Client, message: Message):
        text = message.text.strip()
        
        # Skip commands
        if text.startswith("/"):
            return
        
        user_id = message.from_user.id
        await db.add_user(user_id, message.from_user.username)
        
        query = normalize_name(text)
        
        if len(query) < 2:
            await message.reply_text("❌ Enter at least 2 characters!")
            return
        
        movies = await db.search_movies(query)
        
        if not movies:
            info = await get_movie_info(text)
            if info:
                await message.reply_text(
                    f"❌ **Not in database**\n\n"
                    f"Found on TMDB:\n"
                    f"🎬 {info['title']} ({info.get('year', '')})\n"
                    f"⭐ {info.get('rating', 'N/A')}/10\n\n"
                    f"Contact admin to add!",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await message.reply_text("❌ Movie not found! Check spelling.")
            return
        
        # Single result
        if len(movies) == 1:
            await send_movie_card(bot, message, movies[0])
            return
        
        # Multiple results
        buttons = []
        for m in movies[:10]:
            p = f" ({m.get('parts', 1)}p)" if m.get('parts', 1) > 1 else ""
            buttons.append([InlineKeyboardButton(f"🎬 {m['title']}{p}", callback_data=f"movie:{m['code']}")])
        
        await message.reply_text(
            f"🔍 Found {len(movies)} results:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN
        )


# ============ HELPER FUNCTIONS ============

async def send_welcome(message: Message):
    await message.reply_text(
        "🎬 **Welcome to Movie Bot!**\n\n"
        "Send me any movie name to search.\n\n"
        "**Examples:**\n"
        "• Dune\n"
        "• Avengers\n"
        "• Interstellar",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Channel", url=Config.BACKUP_CHANNEL_LINK)]
        ]),
        parse_mode=ParseMode.MARKDOWN
    )


async def send_movie_card(bot: Client, message: Message, movie: dict):
    info = await get_movie_info(movie["title"])
    
    parts = f"\n📦 Parts: {movie['parts']}" if movie.get('parts', 1) > 1 else ""
    
    if info:
        caption = (
            f"🎬 **{info['title']}** ({info.get('year', '')})\n"
            f"⭐ {info.get('rating', 'N/A')}/10{parts}\n\n"
            f"{info.get('overview', '')[:200]}..."
        )
    else:
        caption = f"🎬 **{movie['title']}**{parts}"
    
    payload = encode_payload(movie["code"])
    link = f"https://t.me/{bot.me.username}?start={payload}"
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📥 Download", url=link)]])
    
    if info and info.get("poster"):
        try:
            await message.reply_photo(info["poster"], caption=caption, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
            return
        except:
            pass
    
    await message.reply_text(caption, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)