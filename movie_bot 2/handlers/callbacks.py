if __name__ == "__main__":
    exit("Run bot.py instead!")

import logging
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import Config
from database import db
from helpers import check_subscription, get_short_link, encode_payload, get_movie_info

logger = logging.getLogger(__name__)


def register_callback_handlers(app: Client):
    
    @app.on_callback_query(filters.regex(r"^movie:"))
    async def movie_cb(bot: Client, query: CallbackQuery):
        code = query.data.split(":")[1]
        movie = await db.get_movie(code)
        
        if not movie:
            await query.answer("❌ Not found!", show_alert=True)
            return
        
        info = await get_movie_info(movie["title"])
        parts = f"\n📦 Parts: {movie['parts']}" if movie.get('parts', 1) > 1 else ""
        
        if info:
            caption = f"🎬 **{info['title']}** ({info.get('year', '')})\n⭐ {info.get('rating', 'N/A')}/10{parts}"
        else:
            caption = f"🎬 **{movie['title']}**{parts}"
        
        payload = encode_payload(code)
        link = f"https://t.me/{bot.me.username}?start={payload}"
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📥 Download", url=link)]])
        
        await query.message.edit_text(caption, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        await query.answer()
    
    
    @app.on_callback_query(filters.regex(r"^part:"))
    async def part_cb(bot: Client, query: CallbackQuery):
        user_id = query.from_user.id
        _, code, part = query.data.split(":")
        part = int(part)
        
        if not await check_subscription(bot, user_id):
            await query.answer("❌ Join channel first!", show_alert=True)
            return
        
        movie = await db.get_movie(code)
        if not movie:
            await query.answer("❌ Not found!", show_alert=True)
            return
        
        token = await db.create_token(user_id, code, part)
        payload = encode_payload(code, part, token)
        final_link = f"https://t.me/{bot.me.username}?start={payload}"
        
        await query.answer("🔄 Generating...")
        
        short = await get_short_link(final_link)
        
        await query.message.edit_text(
            f"✅ **{movie['title']}** - Part {part}\n\n"
            f"Click to download:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔓 Download", url=short)],
                [InlineKeyboardButton("◀️ Back", callback_data=f"back:{code}")]
            ]),
            parse_mode=ParseMode.MARKDOWN
        )
    
    
    @app.on_callback_query(filters.regex(r"^back:"))
    async def back_cb(bot: Client, query: CallbackQuery):
        code = query.data.split(":")[1]
        movie = await db.get_movie(code)
        
        if not movie:
            await query.answer("❌ Not found!", show_alert=True)
            return
        
        buttons = []
        for i in range(1, movie["parts"] + 1):
            buttons.append(InlineKeyboardButton(f"📦 Part {i}", callback_data=f"part:{code}:{i}"))
        
        kb = [buttons[i:i+3] for i in range(0, len(buttons), 3)]
        
        await query.message.edit_text(
            f"🎬 **{movie['title']}**\n\nSelect part:",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.MARKDOWN
        )
        await query.answer()