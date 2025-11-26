if __name__ == "__main__":
    exit("Run bot.py instead!")

import logging
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message
from config import Config
from database import db
from helpers import normalize_name, check_subscription

logger = logging.getLogger(__name__)


def register_admin_handlers(app: Client):
    
    @app.on_message(filters.command("add") & filters.private & filters.user(Config.ADMIN_ID))
    async def add_movie(bot: Client, message: Message):
        if not message.reply_to_message:
            await message.reply_text(
                "📥 **How to add movie:**\n\n"
                "1. Send/forward a video file\n"
                "2. Reply to it with:\n"
                "`/add moviecode Movie Title`\n\n"
                "Example: `/add dune Dune 2021`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        replied = message.reply_to_message
        file_id = None
        
        if replied.video:
            file_id = replied.video.file_id
        elif replied.document:
            file_id = replied.document.file_id
        
        if not file_id:
            await message.reply_text("❌ Reply to a video or document!")
            return
        
        args = message.text.split(None, 2)
        if len(args) < 2:
            await message.reply_text("❌ Usage: `/add code Title`", parse_mode=ParseMode.MARKDOWN)
            return
        
        code = normalize_name(args[1])
        title = args[2] if len(args) > 2 else code.replace("_", " ").title()
        
        await db.add_movie({
            "code": code,
            "title": title,
            "file_ids": [file_id],
            "parts": 1
        })
        
        await message.reply_text(
            f"✅ **Movie Added!**\n\n"
            f"📽️ Title: {title}\n"
            f"🔑 Code: `{code}`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    
    @app.on_message(filters.command("addpart") & filters.private & filters.user(Config.ADMIN_ID))
    async def add_part(bot: Client, message: Message):
        if not message.reply_to_message:
            await message.reply_text(
                "📥 **How to add part:**\n\n"
                "Reply to video with:\n"
                "`/addpart moviecode 2`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        replied = message.reply_to_message
        file_id = replied.video.file_id if replied.video else (replied.document.file_id if replied.document else None)
        
        if not file_id:
            await message.reply_text("❌ Reply to a video or document!")
            return
        
        args = message.text.split()
        if len(args) < 3:
            await message.reply_text("❌ Usage: `/addpart code part_number`", parse_mode=ParseMode.MARKDOWN)
            return
        
        code = normalize_name(args[1])
        try:
            part_num = int(args[2])
        except:
            await message.reply_text("❌ Part number must be a number!")
            return
        
        movie = await db.get_movie(code)
        if not movie:
            await message.reply_text(f"❌ Movie `{code}` not found!", parse_mode=ParseMode.MARKDOWN)
            return
        
        file_ids = movie.get("file_ids", [])
        while len(file_ids) < part_num:
            file_ids.append(None)
        file_ids[part_num - 1] = file_id
        
        movie["file_ids"] = file_ids
        movie["parts"] = len([f for f in file_ids if f])
        await db.add_movie(movie)
        
        await message.reply_text(
            f"✅ **Part {part_num} Added!**\n\n"
            f"📽️ Movie: {movie['title']}\n"
            f"📦 Total Parts: {movie['parts']}",
            parse_mode=ParseMode.MARKDOWN
        )
    
    
    @app.on_message(filters.command("delete") & filters.private & filters.user(Config.ADMIN_ID))
    async def delete_movie(bot: Client, message: Message):
        args = message.text.split(None, 1)
        if len(args) < 2:
            await message.reply_text("❌ Usage: `/delete moviecode`", parse_mode=ParseMode.MARKDOWN)
            return
        
        code = normalize_name(args[1])
        if await db.delete_movie(code):
            await message.reply_text(f"✅ `{code}` deleted!", parse_mode=ParseMode.MARKDOWN)
        else:
            await message.reply_text(f"❌ `{code}` not found!", parse_mode=ParseMode.MARKDOWN)
    
    
    @app.on_message(filters.command("list") & filters.private & filters.user(Config.ADMIN_ID))
    async def list_movies(bot: Client, message: Message):
        movies = await db.get_all_movies()
        if not movies:
            await message.reply_text("📭 No movies yet!")
            return
        
        text = "📽️ **Movies:**\n\n"
        for i, m in enumerate(movies[:50], 1):
            text += f"{i}. `{m['code']}` - {m['title']} ({m.get('parts', 1)}p)\n"
        
        await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    
    
    @app.on_message(filters.command("stats") & filters.private & filters.user(Config.ADMIN_ID))
    async def stats(bot: Client, message: Message):
        users = await db.get_user_count()
        movies = await db.get_all_movies()
        
        await message.reply_text(
            f"📊 **Stats**\n\n"
            f"👥 Users: {users}\n"
            f"🎬 Movies: {len(movies)}",
            parse_mode=ParseMode.MARKDOWN
        )
    
    
    @app.on_message(filters.command("broadcast") & filters.private & filters.user(Config.ADMIN_ID))
    async def broadcast(bot: Client, message: Message):
        if not message.reply_to_message:
            await message.reply_text("❌ Reply to a message to broadcast!")
            return
        
        users = await db.get_all_users()
        sent, failed = 0, 0
        
        status = await message.reply_text("📢 Broadcasting...")
        
        for user in users:
            try:
                await message.reply_to_message.copy(user["user_id"])
                sent += 1
            except:
                failed += 1
        
        await status.edit_text(f"📢 Done!\n✅ Sent: {sent}\n❌ Failed: {failed}")
    
    
    @app.on_message(filters.command("checksub") & filters.private & filters.user(Config.ADMIN_ID))
    async def checksub(bot: Client, message: Message):
        user_id = message.from_user.id
        is_sub = await check_subscription(bot, user_id)
        
        await message.reply_text(
            f"🔍 **Debug Info**\n\n"
            f"Channel ID: `{Config.BACKUP_CHANNEL_ID}`\n"
            f"Your Status: {'✅ Subscribed' if is_sub else '❌ Not Subscribed'}",
            parse_mode=ParseMode.MARKDOWN
        )