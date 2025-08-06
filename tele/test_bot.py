
import sqlite3
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.error import TelegramError

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS groups (
            group_id INTEGER PRIMARY KEY,
            threshold INTEGER DEFAULT 5
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS invites (
            group_id INTEGER,
            user_id INTEGER,
            invite_count INTEGER DEFAULT 0,
            PRIMARY KEY (group_id, user_id)
        )"""
    )
    conn.commit()
    conn.close()

# Get the current threshold for a group
def get_threshold(group_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT threshold FROM groups WHERE group_id = ?", (group_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 5  # Default threshold is 5

# Set the threshold for a group
def set_threshold(group_id, threshold):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO groups (group_id, threshold) VALUES (?, ?)",
        (group_id, threshold),
    )
    conn.commit()
    conn.close()

# Update invite count for a user
def update_invite_count(group_id, user_id, increment=1):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO invites (group_id, user_id, invite_count) "
        "VALUES (?, ?, COALESCE((SELECT invite_count FROM invites WHERE group_id = ? AND user_id = ?), 0) + ?)",
        (group_id, user_id, group_id, user_id, increment),
    )
    conn.commit()
    conn.close()

# Get invite count for a user
def get_invite_count(group_id, user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute(
        "SELECT invite_count FROM invites WHERE group_id = ? AND user_id = ?",
        (group_id, user_id),
    )
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

# Check if a user is an admin
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not update.effective_chat:
        return False
    try:
        admins = await context.bot.get_chat_administrators(update.effective_chat.id)
        return any(admin.user.id == update.effective_user.id for admin in admins)
    except TelegramError:
        return False

# Command to set the invite threshold (admin only)
async def set_threshold_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Only admins can set the threshold.")
        return

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Please provide a number: /setthreshold <number>")
        return

    threshold = int(context.args[0])
    if threshold < 1:
        await update.message.reply_text("Threshold must be at least 1.")
        return

    group_id = update.effective_chat.id
    set_threshold(group_id, threshold)
    await update.message.reply_text(f"Invite threshold set to {threshold} members.")

# Grant messaging permissions to a user
async def grant_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, username: str):
    try:
        await context.bot.restrict_chat_member(
            chat_id,
            user_id,
            permissions={
                "can_send_messages": True,
                "can_send_media_messages": True,
                "can_send_polls": True,
                "can_send_other_messages": True,
                "can_add_web_page_previews": True,
                "can_change_info": False,
                "can_invite_users": True,
                "can_pin_messages": False,
            },
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"@{username or 'User'} has reached the invite threshold and can now send messages!"
        )
    except TelegramError as e:
        logger.error(f"Error granting permissions to user {user_id} in chat {chat_id}: {e}")

# Restrict messaging permissions for a user
async def restrict_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    try:
        await context.bot.restrict_chat_member(
            chat_id,
            user_id,
            permissions={
                "can_send_messages": False,
                "can_send_media_messages": False,
                "can_send_polls": False,
                "can_send_other_messages": False,
                "can_add_web_page_previews": False,
                "can_change_info": False,
                "can_invite_users": True,
                "can_pin_messages": False,
            },
        )
    except TelegramError as e:
        logger.error(f"Error restricting user {user_id} in chat {chat_id}: {e}")

# Handle new members and track invites
async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_message.new_chat_members:
        return

    group_id = update.effective_chat.id
    threshold = get_threshold(group_id)

    for member in update.effective_message.new_chat_members:
        # Skip the bot itself
        if member.id == context.bot.id:
            continue

        # Restrict new members from sending messages by default
        await restrict_user(context, group_id, member.id)

        # Check if the new member was added by someone
        if update.effective_message.from_user:
            inviter_id = update.effective_message.from_user.id
            inviter_username = update.effective_message.from_user.username
            if inviter_id != member.id:  # Ensure the inviter isn't the new member
                update_invite_count(group_id, inviter_id)
                invite_count = get_invite_count(group_id, inviter_id)

                # Immediately grant permissions if threshold is met
                if invite_count >= threshold:
                    await grant_user(context, group_id, inviter_id, inviter_username)
                else:
                    await context.bot.send_message(
                        chat_id=group_id,
                        text=f"@{inviter_username or 'User'} has invited {invite_count} member(s). "
                             f"Need {threshold} to gain messaging permissions."
                    )

# Handle group messages to restrict ineligible users
async def handle_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.effective_user:
        return

    group_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Skip admins and the bot itself
    if await is_admin(update, context) or user_id == context.bot.id:
        return

    # Check invite count
    invite_count = get_invite_count(group_id, user_id)
    threshold = get_threshold(group_id)

    if invite_count < threshold:
        try:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=user_id,
                text=f"You need to invite {threshold} members to send messages in this group. "
                     f"You've invited {invite_count} so far."
            )
        except TelegramError as e:
            logger.error(f"Error handling message from user {user_id}: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

def main():
    # Initialize the database
    init_db()

    # Replace 'YOUR_BOT_TOKEN' with your actual bot token
    application = Application.builder().token().build()

    # Add handlers
    application.add_handler(CommandHandler("setthreshold", set_threshold_command))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, handle_group_message))
    application.add_error_handler(error_handler)

    # Start the bot
    application.run_polling()

if __name__ == "__main__":
    main()
