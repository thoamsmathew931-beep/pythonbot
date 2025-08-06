
import sqlite3
import random
import time
import nest_asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError
import asyncio

# Apply nest_asyncio to handle nested event loops
nest_asyncio.apply()


# Initialize SQLite database
def init_db():
    conn = sqlite3.connect('lanka_legends.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS players
                 (
                     user_id
                     INTEGER
                     PRIMARY
                     KEY,
                     username
                     TEXT,
                     level
                     INTEGER
                     DEFAULT
                     0,
                     lives
                     INTEGER
                     DEFAULT
                     2,
                     current_game
                     INTEGER
                     DEFAULT
                     0,
                     invites
                     INTEGER
                     DEFAULT
                     0,
                     start_time
                     REAL,
                     failures
                     INTEGER
                     DEFAULT
                     0,
                     score
                     INTEGER
                     DEFAULT
                     0
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS invites
                 (
                     inviter_id
                     INTEGER,
                     invitee_id
                     INTEGER,
                     timestamp
                     REAL
                 )''')
    conn.commit()
    return conn


# Game definitions
GAMES = {
    'trivia': {
        'easy': [('What’s the capital of Sri Lanka?', 'Colombo'), ('Which animal is on the SL flag?', 'Lion')],
        'medium': [('What’s the highest peak in SL?', 'Pidurutalagala'), ('What’s the longest river?', 'Mahaweli')],
        'hard': [('Who was SL’s first Prime Minister?', 'D.S. Senanayake'),
                 ('What year did SL gain independence?', '1948')]
    },
    'dice_duel': {'easy': 4, 'medium': 6, 'hard': 8},  # Target number to beat
    'tap_fast': {'easy': 5, 'medium': 10, 'hard': 15},  # Taps needed in 5 seconds
    'math_battle': {'easy': ('2 + 3', '5'), 'medium': ('15 * 3', '45'), 'hard': ('7 * 13', '91')},  # Expression, answer
    'lucky_box': {'easy': 3, 'medium': 5, 'hard': 7},  # Number of boxes
    'emoji_memory': {
        'easy': ('😀😺😀', '😀😺😀'),
        'medium': ('😺🐘😀😺🐘', '😺🐘😀😺🐘'),
        'hard': ('🐘😺😀🐘😺😀', '🐘😺😀🐘😺😀')
    }
}


# Bot class
class LankaLegendsBot:
    def __init__(self):
        self.conn = init_db()
        self.games = GAMES
        self.level_requirements = {1: 1, 2: 2, 3: 2}  # Invites needed per level

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        c = self.conn.cursor()
        c.execute('SELECT * FROM players WHERE user_id = ?', (user.id,))
        player = c.fetchone()

        print(f"/start called by user {user.id} ({user.username or user.first_name})")  # Debug

        if not player:
            c.execute('INSERT INTO players (user_id, username, start_time) VALUES (?, ?, ?)',
                      (user.id, user.username or user.first_name, time.time()))
            self.conn.commit()
            await update.message.reply_text(
                "<b>🇱🇰 Welcome to Lanka Legends: Invite & Conquer! 😎</b>\n"
                "Invite 1 friend to join the game! Use /profile to check your status.",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                "<b>Aiyo, you’re already in the game! 😜</b>\nCheck /profile or keep inviting!",
                parse_mode=ParseMode.HTML
            )

    async def profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        c = self.conn.cursor()
        c.execute('SELECT * FROM players WHERE user_id = ?', (user.id,))
        player = c.fetchone()

        print(f"/profile called by user {user.id}")  # Debug

        if not player:
            await update.message.reply_text("You haven’t started yet! Use /start to join. 😎")
            return

        level, lives, current_game, invites, start_time, failures, score = player[2:]
        minutes = int((time.time() - start_time) / 60) if start_time else 0
        username = player[1] or "Unknown"

        await update.message.reply_text(
            "<b>🎮 Your Profile 🎮</b>\n"
            f"Username: {username}\n"
            f"Level: {level}\n"
            f"Lives: {lives}\n"
            f"Current Game: {'Game ' + str(current_game + 1) if level > 0 else 'Not started'}\n"
            f"Invites: {invites}\n"
            f"Time Taken: {minutes} mins\n"
            f"Failures: {failures}\n"
            f"Score: {score}\n"
            "Invite more to progress! 🇱🇰",
            parse_mode=ParseMode.HTML
        )

    async def leaderboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        c = self.conn.cursor()
        c.execute(
            'SELECT username, start_time, failures, score FROM players WHERE score > 0 ORDER BY score DESC LIMIT 5')
        leaders = c.fetchall()

        print(f"/leaderboard called")  # Debug

        if not leaders:
            await update.message.reply_text("No legends yet! Be the first! 🏆")
            return

        text = "<b>🏆 Lanka Legends Leaderboard 🏆</b>\n\n"
        for i, (username, start_time, failures, score) in enumerate(leaders, 1):
            minutes = int((time.time() - start_time) / 60) if start_time else 0
            text += f"{i}. {username} - Score: {score} (Time: {minutes}m, Fails: {failures})\n"

        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def handle_invite(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message.new_chat_members:
            print("No new chat members detected")  # Debug
            return

        inviter_id = update.effective_user.id
        inviter_name = update.effective_user.username or update.effective_user.first_name
        print(f"Invite detected by user {inviter_id} ({inviter_name})")  # Debug

        for member in update.message.new_chat_members:
            if member.is_bot:
                print(f"Ignoring bot invite: {member.id}")  # Debug
                continue  # Skip bots
            c = self.conn.cursor()
            c.execute('SELECT invites FROM players WHERE user_id = ?', (inviter_id,))
            player = c.fetchone()
            if player:
                invites = player[0] + 1
                c.execute('UPDATE players SET invites = ? WHERE user_id = ?', (invites, inviter_id))
                c.execute('INSERT INTO invites (inviter_id, invitee_id, timestamp) VALUES (?, ?, ?)',
                          (inviter_id, member.id, time.time()))
                self.conn.commit()
                print(f"Updated invites for {inviter_id}: {invites}")  # Debug
                await update.message.reply_text(
                    f"Aiyo, {inviter_name} invited someone! 😎 Invites: {invites}",
                    parse_mode=ParseMode.HTML
                )
                await self.check_level_progress(update, context, inviter_id)
            else:
                print(f"No player found for user {inviter_id}")  # Debug
                await update.message.reply_text(
                    f"<b>Aiyo, {inviter_name}!</b> You need to use /start first to join the game! 😜",
                    parse_mode=ParseMode.HTML
                )

    async def check_level_progress(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
        c = self.conn.cursor()
        c.execute('SELECT level, invites, lives, current_game FROM players WHERE user_id = ?', (user_id,))
        player = c.fetchone()
        if not player:
            print(f"No player found for user {user_id} in check_level_progress")  # Debug
            return

        level, invites, lives, current_game = player
        required_invites = self.level_requirements.get(level + 1, 0)

        print(
            f"Checking progress for user {user_id}: level {level}, invites {invites}, required {required_invites}")  # Debug
        if invites >= required_invites and level < 3:
            c.execute('UPDATE players SET level = ?, lives = 2, current_game = 0 WHERE user_id = ?',
                      (level + 1, user_id))
            self.conn.commit()
            print(f"User {user_id} advanced to level {level + 1}")  # Debug
            await update.message.reply_text(
                f"<b>🎉 Congrats! You’ve reached Level {level + 1}! Let’s play a game! 😎</b>",
                parse_mode=ParseMode.HTML
            )
            await self.start_game(update, context, user_id)
        else:
            print(
                f"User {user_id} not advanced: invites {invites} < required {required_invites} or level {level} >= 3")  # Debug

    async def start_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
        c = self.conn.cursor()
        c.execute('SELECT level, current_game FROM players WHERE user_id = ?', (user_id,))
        player = c.fetchone()
        if not player or player[0] == 0:
            print(f"No game started for user {user_id}: level 0 or no player")  # Debug
            return

        level, current_game = player
        difficulty = {1: 'easy', 2: 'medium', 3: 'hard'}[level]
        game_type = random.choice(list(self.games.keys()))

        print(f"Starting {game_type} for user {user_id}, level {level}, game {current_game + 1}")  # Debug

        if game_type == 'trivia':
            question, answer = random.choice(self.games['trivia'][difficulty])
            await update.message.reply_text(
                f"<b>🧠 Trivia Time!</b> {question}\nReply with your answer!",
                parse_mode=ParseMode.HTML
            )
            context.user_data['game'] = {'type': 'trivia', 'answer': answer, 'level': level, 'game_num': current_game}
        elif game_type == 'dice_duel':
            target = self.games['dice_duel'][difficulty]
            await update.message.reply_text(
                f"<b>🎲 Dice Duel!</b> Roll a number higher than {target} using /roll!\nReply with /roll",
                parse_mode=ParseMode.HTML
            )
            context.user_data['game'] = {'type': 'dice_duel', 'target': target, 'level': level,
                                         'game_num': current_game}
        elif game_type == 'tap_fast':
            target = self.games['tap_fast'][difficulty]
            await update.message.reply_text(
                f"<b>👆 Tap Fast!</b> Send 'tap' {target} times in 5 seconds!\nStart now!",
                parse_mode=ParseMode.HTML
            )
            context.user_data['game'] = {
                'type': 'tap_fast', 'target': target, 'level': level, 'game_num': current_game,
                'start_time': time.time(), 'taps': 0
            }
        elif game_type == 'math_battle':
            expression, answer = self.games['math_battle'][difficulty]
            await update.message.reply_text(
                f"<b>🧮 Math Battle!</b> Solve: {expression}\nReply with the answer!",
                parse_mode=ParseMode.HTML
            )
            context.user_data['game'] = {'type': 'math_battle', 'answer': answer, 'level': level,
                                         'game_num': current_game}
        elif game_type == 'lucky_box':
            num_boxes = self.games['lucky_box'][difficulty]
            winning_box = random.randint(1, num_boxes)
            await update.message.reply_text(
                f"<b>🎁 Pick a Lucky Box!</b> Choose a number from 1 to {num_boxes}\nReply with a number!",
                parse_mode=ParseMode.HTML
            )
            context.user_data['game'] = {'type': 'lucky_box', 'winning_box': winning_box, 'level': level,
                                         'game_num': current_game}
        elif game_type == 'emoji_memory':
            sequence, answer = self.games['emoji_memory'][difficulty]
            await update.message.reply_text(
                f"<b>🧠 Emoji Memory!</b> Memorize this: {sequence}\nReply with the exact sequence!",
                parse_mode=ParseMode.HTML
            )
            context.user_data['game'] = {'type': 'emoji_memory', 'answer': answer, 'level': level,
                                         'game_num': current_game}

    async def handle_game_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if 'game' not in context.user_data:
            print(f"No active game for user {update.effective_user.id}")  # Debug
            return

        user = update.effective_user
        c = self.conn.cursor()
        game = context.user_data['game']
        text = update.message.text

        print(f"Processing response for user {user.id}: {text}")  # Debug

        if game['type'] == 'trivia':
            correct = text.lower() == game['answer'].lower()
            await self.process_game_result(update, context, user.id, correct)
        elif game['type'] == 'dice_duel':
            if text == '/roll':
                roll = random.randint(1, 6)
                correct = roll >= game['target']
                await update.message.reply_text(
                    f"You rolled a {roll}! {'<b>Win!</b>' if correct else '<b>Lose!</b>'}",
                    parse_mode=ParseMode.HTML
                )
                await self.process_game_result(update, context, user.id, correct)
        elif game['type'] == 'tap_fast':
            if text.lower() == 'tap' and time.time() - game['start_time'] <= 5:
                game['taps'] += 1
                print(f"Tap count for user {user.id}: {game['taps']}")  # Debug
                if game['taps'] >= game['target']:
                    await update.message.reply_text("<b>Win!</b> You tapped fast enough! 😎", parse_mode=ParseMode.HTML)
                    await self.process_game_result(update, context, user.id, True)
                context.user_data['game'] = game  # Update tap count
                return  # Don't clear game yet
            elif time.time() - game['start_time'] > 5:
                await update.message.reply_text(
                    f"<b>Lose!</b> Time’s up! You got {game['taps']} taps, needed {game['target']}.",
                    parse_mode=ParseMode.HTML
                )
                await self.process_game_result(update, context, user.id, False)
        elif game['type'] == 'math_battle':
            correct = text == game['answer']
            await self.process_game_result(update, context, user.id, correct)
        elif game['type'] == 'lucky_box':
            try:
                choice = int(text)
                correct = choice == game['winning_box']
                await self.process_game_result(update, context, user.id, correct)
            except ValueError:
                await update.message.reply_text("Please reply with a number!", parse_mode=ParseMode.HTML)
                return
        elif game['type'] == 'emoji_memory':
            correct = text == game['answer']
            await self.process_game_result(update, context, user.id, correct)

        if 'game' in context.user_data and game['type'] != 'tap_fast':
            del context.user_data['game']

    async def process_game_result(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, won):
        c = self.conn.cursor()
        c.execute('SELECT level, lives, current_game, failures, start_time FROM players WHERE user_id = ?', (user_id,))
        player = c.fetchone()
        level, lives, current_game, failures, start_time = player

        print(
            f"Game result for user {user_id}: {'Win' if won else 'Lose'}, level {level}, game {current_game + 1}")  # Debug

        if won:
            current_game += 1
            if current_game >= 2:  # Completed level
                if level == 3:
                    minutes = int((time.time() - start_time) / 60)
                    score = 1000 - (minutes * 5) - (failures * 20)
                    c.execute('UPDATE players SET score = ?, level = 4 WHERE user_id = ?', (score, user_id))
                    self.conn.commit()
                    await update.message.reply_text(
                        f"<b>🏆 Legend Alert!</b> You’ve conquered all levels! 🥳 Final Score: {score}",
                        parse_mode=ParseMode.HTML
                    )
                    return
                c.execute('UPDATE players SET current_game = 0, lives = 2 WHERE user_id = ?', (user_id,))
                self.conn.commit()
                await update.message.reply_text(
                    f"<b>🎉 You won!</b> On to the next game in Level {level}! 😎",
                    parse_mode=ParseMode.HTML
                )
            else:
                c.execute('UPDATE players SET current_game = ? WHERE user_id = ?', (current_game, user_id))
                self.conn.commit()
                await update.message.reply_text(
                    f"<b>🎉 Nice one!</b> Next game coming up! 😎",
                    parse_mode=ParseMode.HTML
                )
            await self.start_game(update, context, user_id)
        else:
            lives -= 1
            failures += 1
            if lives == 0:
                c.execute('UPDATE players SET lives = 2, current_game = 0, failures = ?, invites = 0 WHERE user_id = ?',
                          (failures, user_id))
                self.conn.commit()
                await update.message.reply_text(
                    f"<b>Aiyo, game over!</b> 😜 Invite 1 more person to retry Level {level}.",
                    parse_mode=ParseMode.HTML
                )
            else:
                c.execute('UPDATE players SET lives = ?, failures = ? WHERE user_id = ?', (lives, failures, user_id))
                self.conn.commit()
                await update.message.reply_text(
                    f"<b>Oops, wrong!</b> 😅 Lives left: {lives}. Try again!",
                    parse_mode=ParseMode.HTML
                )
                await self.start_game(update, context, user_id)

    async def force_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manually trigger a game for testing."""
        user_id = update.effective_user.id
        print(f"/forcegame called by user {user_id}")  # Debug
        c = self.conn.cursor()
        c.execute('SELECT level FROM players WHERE user_id = ?', (user_id,))
        player = c.fetchone()
        if not player or player[0] == 0:
            await update.message.reply_text(
                "<b>Aiyo!</b> You need to be on Level 1 or higher. Use /start and invite someone first! 😜",
                parse_mode=ParseMode.HTML
            )
            return
        await self.start_game(update, context, user_id)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors and notify the user."""
        try:
            raise context.error
        except TelegramError as e:
            print(f"Error: {e}")  # Log the error
            if update and update.message:
                await update.message.reply_text(
                    "Aiyo, something went wrong! 😅 Please try again or contact the admin.",
                    parse_mode=ParseMode.HTML
                )


async def main():
    app = Application.builder().token('').build()
    bot = LankaLegendsBot()

    app.add_handler(CommandHandler('start', bot.start))
    app.add_handler(CommandHandler('profile', bot.profile))
    app.add_handler(CommandHandler('leaderboard', bot.leaderboard))
    app.add_handler(CommandHandler('forcegame', bot.force_game))  # Added for testing
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot.handle_invite))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_game_response))
    app.add_error_handler(bot.error_handler)

    await app.run_polling()


if __name__ == '__main__':
    asyncio.run(main())
