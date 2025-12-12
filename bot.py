import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import yt_dlp
from config import Config

# Validate config before starting
Config.validate()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- Helper Functions ---

def get_youtube_info(url):
    """Extracts video info without downloading."""
    ydl_opts = {'quiet': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return info
        except Exception as e:
            print(f"Error extracting info: {e}")
            return None

def download_media(url, format_type, resolution=None):
    """
    Downloads media.
    format_type: 'video' or 'audio'
    resolution: '1080', '720', etc. or 'best'
    """
    ydl_opts = {
        'quiet': True,
        'max_filesize': Config.MAX_FILE_SIZE,
        'outtmpl': '%(title)s.%(ext)s',
    }

    if format_type == 'audio':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    elif format_type == 'video':
        if resolution and resolution != 'best':
            # Specific resolution
            ydl_opts['format'] = f'bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]'
        else:
            # Best available
            ydl_opts['format'] = 'best[ext=mp4]/best'
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if format_type == 'audio':
                base, _ = os.path.splitext(filename)
                filename = base + ".mp3"
                
            return filename
        except Exception as e:
            print(f"Download failed: {e}")
            return None

# --- Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! Send me a link.\n"
        "I support YouTube (with quality selection) and Instagram."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    
    if not url.startswith(('http://', 'https://')):
        await update.message.reply_text("Please send a valid link.")
        return

    context.user_data['current_url'] = url
    
    # Check if it's YouTube
    if "youtube.com" in url or "youtu.be" in url:
        status_msg = await update.message.reply_text("Analyzing YouTube link...")
        
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, get_youtube_info, url)
        
        if not info:
            await status_msg.edit_text("Could not fetch video info.")
            return

        # Find available resolutions
        formats = info.get('formats', [])
        resolutions = set()
        for f in formats:
            if f.get('height'):
                resolutions.add(f['height'])
        
        # Create buttons for resolutions
        keyboard = []
        sorted_res = sorted([r for r in resolutions if r >= 144], reverse=True)
        common_res = [1080, 720, 480, 360]
        
        row = []
        for res in sorted_res:
            if res in common_res:
                # Callback: "qual|{resolution}" -> leads to format selection
                row.append(InlineKeyboardButton(f"{res}p", callback_data=f"qual|{res}"))
        if row:
            keyboard.append(row)
            
        keyboard.append([InlineKeyboardButton("Audio Only (MP3)", callback_data="dl|audio|file")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await status_msg.edit_text(f"Select quality for: {info.get('title', 'Video')}", reply_markup=reply_markup)

    else:
        # Instagram / Other
        keyboard = [
            [
                InlineKeyboardButton("Video (Stream)", callback_data="dl|best|video"),
                InlineKeyboardButton("Video (File)", callback_data="dl|best|file")
            ],
            [InlineKeyboardButton("Audio Only", callback_data="dl|audio|file")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Choose format:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('|')
    action = data[0]
    
    url = context.user_data.get('current_url')
    if not url:
        await query.edit_message_text("Session expired. Please send the link again.")
        return

    # --- Step 1: Quality Selected (YouTube) ---
    if action == 'qual':
        res = data[1]
        # Ask for Video vs File
        keyboard = [
            [
                InlineKeyboardButton("Video (Stream)", callback_data=f"dl|{res}|video"),
                InlineKeyboardButton("File (Document)", callback_data=f"dl|{res}|file")
            ],
            [InlineKeyboardButton("<< Back", callback_data="back_to_main")] # Simplified back
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Selected {res}p. How do you want to receive it?", reply_markup=reply_markup)
        return

    # --- Step 2: Download & Send ---
    elif action == 'dl':
        # data format: dl | resolution/type | mode
        res_or_type = data[1] # '1080', 'best', or 'audio'
        mode = data[2]        # 'video' or 'file'
        
        await query.edit_message_text(f"Downloading...")
        
        loop = asyncio.get_running_loop()
        
        if res_or_type == 'audio':
             filename = await loop.run_in_executor(None, download_media, url, 'audio', None)
        else:
             filename = await loop.run_in_executor(None, download_media, url, 'video', res_or_type)

        if filename and os.path.exists(filename):
            await query.message.reply_text("Uploading...")
            
            with open(filename, 'rb') as f:
                if res_or_type == 'audio':
                    await query.message.reply_audio(f)
                elif mode == 'file':
                    await query.message.reply_document(f)
                else:
                    await query.message.reply_video(f)
            
            os.remove(filename)
        else:
            await query.message.reply_text("Failed to download (Check size limit or FFmpeg).")

    elif action == 'back_to_main':
        await query.message.reply_text("Please send the link again to restart.")

if __name__ == '__main__':
    application = ApplicationBuilder().token(Config.BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Bot is running...")
    application.run_polling()
