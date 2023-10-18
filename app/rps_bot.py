import discord
import os
import pymysql
import logging
import random
from datetime import datetime
from discord.ext import commands, tasks
from discord.ui import View
from discord import Embed
from dotenv import load_dotenv
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB

load_dotenv()
command_flag = os.getenv("SEARCHFI_BOT_FLAG")
bot_token = os.getenv("SHOPPING_BOT_TOKEN")
shopping_channel_id = os.getenv("SHOPPING_CHANNEL_ID")
gameroom_channel_id = os.getenv("GAMEROOM_CHANNEL_ID")
giveup_token_channel_id = os.getenv("GIVEUP_TOKEN_CHANNEL_ID")
mysql_ip = os.getenv("MYSQL_IP")
mysql_port = os.getenv("MYSQL_PORT")
mysql_id = os.getenv("MYSQL_ID")
mysql_passwd = os.getenv("MYSQL_PASSWD")
mysql_db = os.getenv("MYSQL_DB")
guild_ids = list(map(int, os.getenv('GUILD_ID').split(',')))
bot_log_folder = os.getenv("BOT_LOG_FOLDER")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(filename=f"{bot_log_folder}/rps_bot.log", mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, host, port, user, password, db):
        self.pool = PooledDB(
            creator=pymysql,
            maxconnections=5,
            mincached=2,
            host=host,
            port=int(port),
            user=user,
            password=password,
            database=db,
            charset='utf8mb4',
            cursorclass=DictCursor
        )

    def get_connection(self):
        return self.pool.connection()


bot = commands.Bot(command_prefix=command_flag, intents=discord.Intents.all())
db = Database(mysql_ip, mysql_port, mysql_id, mysql_passwd, mysql_db)


async def save_tokens(params):
    connection = db.get_connection()
    cursor = connection.cursor()
    result = 0
    try:
        user_id = params.get('user_id')
        token = params.get('token')

        cursor.execute("""
            select tokens
            from user_tokens
            where user_id = %s
        """, (str(user_id),))
        user = cursor.fetchone()

        if user:
            before_user_tokens = user.get('tokens')
            user_tokens = int(before_user_tokens)
            user_tokens += token

            if user_tokens < 0:
                user_tokens = 0

            cursor.execute("""
                update user_tokens set tokens = %s
                where user_id = %s
            """, (user_tokens, str(user_id),))
        else:
            before_user_tokens = 0
            user_tokens = token

            cursor.execute("""
                insert into user_tokens (user_id, tokens)
                values (%s, %s)
            """, (str(user_id), user_tokens,))

        connection.commit()
        result = {
            'success': 1,
            'before_user_tokens': before_user_tokens,
            'after_user_tokens': user_tokens
        }
    except Exception as e:
        logger.error(f'save_tokens error: {e}')
        connection.rollback()
        result = {
            'success': 0,
            'before_user_tokens': 0,
            'after_user_tokens': 0
        }
    finally:
        cursor.close()
        connection.close()
        return result


class RPSGameView(View):
    def __init__(self, bot, challenger, opponent, amount):
        super().__init__(timeout=10)
        self.bot = bot
        self.challenger = challenger
        self.opponent = opponent
        self.time_left = 10
        self.message = None
        self.amount = amount

    async def send_initial_message(self, ctx):
        embed = Embed(
            title='RPS Game',
            description=f"{self.opponent.mention}! {self.challenger.name}님이 {self.amount}개 토큰을 걸고 가위바위보 게임을 신청하셨습니다. 수락하시겠습니까?\n남은 시간: {self.time_left}초\n\n"
                        f"{self.opponent.mention}! {self.challenger.name} has signed up for rock-paper-scissors with {self.amount} tokens. Would you like to accept it?\nTime remaining: {self.time_left} seconds\n\n",
            color=0xFFFFFF,
        )
        self.message = await ctx.send(embed=embed, view=self)
        self.update_timer.start()

    @tasks.loop(seconds=1)  # 1초마다 업데이트
    async def update_timer(self):
        self.time_left -= 1
        if self.time_left < 0:
            self.update_timer.stop()
            embed = Embed(
                title='Response Timeout',
                description=f"{self.opponent.name}님이 응답 시간을 초과하셨습니다.\n\n{self.opponent.name} has exceeded its response time.",
                color=0xff0000,
            )
            await self.message.edit(embed=embed, view=None)

            self.bot.get_cog('RPSGame').active_games[self.challenger.id] = False
            self.bot.get_cog('RPSGame').active_games[self.opponent.id] = False

            return
        embed = Embed(
            title='RPS Game',
            description=f"{self.opponent.mention}! {self.challenger.name}님이 {self.amount}개 토큰을 걸고 가위바위보 게임을 신청하셨습니다. 수락하시겠습니까?\n남은 시간: {self.time_left}초\n\n"
                        f"{self.opponent.mention}! {self.challenger.name} has signed up for rock-paper-scissors with {self.amount} tokens. Would you like to accept it?\nTime remaining: {self.time_left} seconds\n\n",
            color=0xFFFFFF,
        )
        await self.message.edit(embed=embed)

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.primary)
    async def accept(self, button, interaction):
        if interaction.user.id != self.opponent.id:
            embed = Embed(
                title='Permission Denied',
                description=f"❌ 이 버튼을 누를 권한이 없습니다.\n\n❌ You do not have permission to press this button.",
                color=0xff0000,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        self.update_timer.stop()  # 타이머 중지
        # 게임 시작
        choices = [
            {
                'name': '가위(Scissors)',
                'emoji': ':v:'
            },
            {
                'name': '바위(Rock)',
                'emoji': ':fist:'
            },
            {
                'name': '보(Paper)',
                'emoji': ':raised_back_of_hand:'
            }
        ]
        author_choice = random.choice(choices)
        opponent_choice = random.choice(choices)

        # 결과 계산
        if author_choice == opponent_choice:
            result = ":zany_face: 무승부(Draw)"
            description = f"{self.challenger.name}: {author_choice['emoji']}{author_choice['name']}\n{self.opponent.name}: {opponent_choice['emoji']}{opponent_choice['name']}\n\nResult: {result}\n\n"
            embed = Embed(
                title='✅ RPS Result',
                description=description,
                color=0xFFFFFF,
            )
            await self.message.edit(embed=embed, view=None)
        elif (author_choice['name'] == "가위(Scissors)" and opponent_choice['name'] == "보(Paper)") \
                or (author_choice['name'] == "바위(Rock)" and opponent_choice['name'] == "가위(Scissors)") \
                or (author_choice['name'] == "보(Paper)" and opponent_choice['name'] == "바위(Rock)"):
            result = f"{self.challenger.mention} is Winner!"
            description = f"{self.challenger.name}: {author_choice['emoji']}{author_choice['name']}\n" \
                          f"{self.opponent.name}: {opponent_choice['emoji']}{opponent_choice['name']}\n\nResult: {result}\n\n"
            await save_rps_tokens(interaction, self.challenger, self.opponent, self.amount, description)
        else:
            result = f"{self.opponent.mention} is Winner!"
            description = f"{self.challenger.name}: {author_choice['emoji']}{author_choice['name']}\n" \
                          f"{self.opponent.name}: {opponent_choice['emoji']}{opponent_choice['name']}\n\nResult: {result}\n\n"
            await save_rps_tokens(interaction, self.opponent, self.challenger, self.amount, description)

        self.bot.get_cog('RPSGame').active_games[self.challenger.id] = False
        self.bot.get_cog('RPSGame').active_games[self.opponent.id] = False

        self.stop()  # View를 중지하고 버튼을 비활성화

    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def decline(self, button, interaction):
        if interaction.user.id != self.opponent.id:
            embed = Embed(
                title='Permission Denied',
                description=f"❌ 이 버튼을 누를 권한이 없습니다.\n\n❌ You do not have permission to press this button.",
                color=0xff0000,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        self.update_timer.stop()  # 타이머 중지
        embed = Embed(
            title='Opponent Reject',
            description=f"❌ {self.opponent.name}님이 게임을 거부하셨습니다.\n\n❌ {self.opponent.name} rejected the game.",
            color=0xff0000,
        )
        await interaction.channel.send(embed=embed)

        self.bot.get_cog('RPSGame').active_games[self.challenger.id] = False
        self.bot.get_cog('RPSGame').active_games[self.opponent.id] = False

        self.stop()  # View를 중지하고 버튼을 비활성화


class RPSGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_played_date = {}  # user_id를 키로 하고 마지막으로 게임을 한 날짜를 값으로 가지는 딕셔너리
        self.active_games = {}  # user_id를 키로 하고 게임 상태를 값으로 가지는 딕셔너리

    @commands.command()
    async def rps(self, ctx, opponent: discord.Member, amount=1):
        # gameroom_channel_id 채널에서는 제한 없이 게임 가능
        if ctx.channel.id != int(gameroom_channel_id):
            # 해당 유저가 마지막으로 게임을 한 날짜 가져오기
            last_date = self.last_played_date.get(ctx.author.id)

            # 유저가 오늘 이미 게임을 한 경우 에러 메시지 보내기
            if last_date and last_date == datetime.utcnow().date():
                embed = Embed(
                    title='Game Error',
                    description=f"❌ 이 채널에서는 하루에 한 번만 게임을 할 수 있습니다.\n<#{gameroom_channel_id}>에서는 제한없이 가능합니다.\n\n"
                                f"❌ You can only play once a day in this channel.\nYou can play without limits in <#{gameroom_channel_id}>.",
                    color=0xff0000,
                )
                await ctx.reply(embed=embed, mention_author=True)
                return

        if self.active_games.get(ctx.author.id) or self.active_games.get(opponent.id):
            embed = Embed(
                title='Game Error',
                description="❌ 이미 게임이 진행중인 유저가 있습니다.\n\n❌ There is a user who is already playing the game.",
                color=0xff0000,
            )
            await ctx.reply(embed=embed, mention_author=True)
            return

        if ctx.author.id == opponent.id:
            embed = Embed(
                title='Game Error',
                description="❌ 자신과는 게임을 진행할 수 없습니다.\n\n❌ You can't play with yourself.",
                color=0xff0000,
            )
            await ctx.reply(embed=embed, mention_author=True)
            return

        if abs(amount) > 20:
            embed = Embed(
                title='Game Error',
                description=f"❌ 최대 20개의 토큰만 가능합니다.\n\n"
                            f"❌ You can only have a maximum of 20 tokens.",
                color=0xff0000,
            )
            await ctx.reply(embed=embed, mention_author=True)
            return

        connection = db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                select tokens
                from user_tokens
                where user_id = %s
            """, ctx.author.id)
            user = cursor.fetchone()
            if not user:
                user_tokens = 0
            else:
                user_tokens = int(user['tokens'])

            if abs(amount) > user_tokens:
                embed = Embed(
                    title='Insufficient Tokens',
                    description="❌ 보유한 토큰이 부족합니다. \n\n❌ Token holding quantity is insufficient.",
                    color=0xff0000,
                )
                await ctx.reply(embed=embed, mention_author=True)
                return

            cursor.execute("""
                select tokens
                from user_tokens
                where user_id = %s
            """, opponent.id)
            user = cursor.fetchone()
            if not user:
                user_tokens = 0
            else:
                user_tokens = int(user['tokens'])

            if abs(amount) > user_tokens:
                embed = Embed(
                    title='Insufficient Tokens',
                    description="❌ 상대방이 보유한 토큰이 부족합니다. \n\n❌ Opponent does not have enough tokens.",
                    color=0xff0000,
                )
                await ctx.reply(embed=embed, mention_author=True)
                return

            game_view = RPSGameView(self.bot, ctx.author, opponent, amount)
            await game_view.send_initial_message(ctx)

            self.active_games[ctx.author.id] = True
            self.active_games[opponent.id] = True

            if ctx.channel.id != int(gameroom_channel_id):
                self.last_played_date[ctx.author.id] = datetime.utcnow().date()
        except Exception as e:
            logger.error(f'rps error: {e}')
            self.active_games[ctx.author.id] = False
            self.active_games[opponent.id] = False
            connection.rollback()
        finally:
            cursor.close()
            connection.close()


async def save_rps_tokens(interaction, winner, loser, amount, description):
    try:
        params = {
            'user_id': winner.id,
            'token': int(amount),
        }

        result = await save_tokens(params)

        if result.get('success') > 0:
            description += f"Successfully gave `{params.get('token')}` tokens to {winner.mention}\n" \
                           f"{winner.mention} tokens: `{result.get('before_user_tokens')}` -> `{result.get('after_user_tokens')}`\n\n"

        params = {
            'user_id': loser.id,
            'token': int(amount) * (-1),
        }

        result = await save_tokens(params)

        if result.get('success') > 0:
            description += f"Successfully removed `{params.get('token')}` tokens to {loser.mention}\n" \
                           f"{loser.mention} tokens: `{result.get('before_user_tokens')}` -> `{result.get('after_user_tokens')}`"

            embed = Embed(
                title='✅ RPS Result',
                description=description,
                color=0xFFFFFF,
            )
            await interaction.channel.send(embed=embed)
    except Exception as e:
        logger.error(f'save_rps_tokens error: {e}')


class RPSGame2View(View):
    def __init__(self, ctx, challenger, opponent, amount):
        super().__init__(timeout=10)
        self.ctx = ctx
        self.time_left = 10
        self.challenger = challenger
        self.opponent = opponent
        self.amount = amount
        self.author_choice = None
        self.opponent_choice = None
        self.message = None

    async def send_initial_message(self, ctx):
        embed = Embed(
            title='RPS Game 2',
            description=f"{self.opponent.mention}! {self.challenger.name}님이 {self.amount}개 토큰을 걸고 가위바위보 게임을 신청하셨습니다. 수락하신다면 아래 버튼을 선택해주세요.\n남은 시간: {self.time_left}초\n\n"
                        f"{self.opponent.mention}! {self.challenger.name} has signed up for rock-paper-scissors with {self.amount} tokens. If you accept, please select the button below.\nTime remaining: {self.time_left} seconds\n\n",
            color=0xFFFFFF,
        )
        self.message = await ctx.send(embed=embed, view=self)
        self.update_timer.start()

    @tasks.loop(seconds=1)
    async def update_timer(self):
        self.time_left -= 1
        if self.time_left < 0:
            self.update_timer.stop()
            no_choice_user = ""
            if not self.author_choice:
                no_choice_user += f"{self.challenger.name}, "
            if not self.opponent_choice:
                no_choice_user += f"{self.opponent.name}, "
            embed = Embed(
                title='Response Timeout',
                description=f"{no_choice_user[:-2]}님이 응답 시간을 초과하셨습니다.\n\n{no_choice_user[:-2]} has exceeded its response time.",
                color=0xff0000,
            )
            await self.message.edit(embed=embed, view=None)
            return
        embed = Embed(
            title='RPS Game 2',
            description=f"{self.opponent.mention}! {self.challenger.name}님이 {self.amount}개 토큰을 걸고 가위바위보 게임을 신청하셨습니다. 수락하신다면 아래 버튼을 선택해주세요.\n남은 시간: {self.time_left}초\n\n"
                        f"{self.opponent.mention}! {self.challenger.name} has signed up for rock-paper-scissors with {self.amount} tokens. If you accept, please select the button below.\nTime remaining: {self.time_left} seconds\n\n",
            color=0xFFFFFF,
        )
        await self.message.edit(embed=embed)

    async def resolve_game(self):
        self.update_timer.stop()  # 타이머 중지
        # 게임 시작
        choices = [
            {
                'name': '가위(Scissors)',
                'emoji': ':v:'
            },
            {
                'name': '바위(Rock)',
                'emoji': ':fist:'
            },
            {
                'name': '보(Paper)',
                'emoji': ':raised_back_of_hand:'
            }
        ]
        author_choice = next((choice for choice in choices if choice['name'] == self.author_choice), None)
        opponent_choice = next((choice for choice in choices if choice['name'] == self.opponent_choice), None)
        # 결과 계산
        if author_choice == opponent_choice:
            result = ":zany_face: 무승부(Draw)"
            description = f"{self.challenger.name}: {author_choice['emoji']}{author_choice['name']}\n{self.opponent.name}: {opponent_choice['emoji']}{opponent_choice['name']}\n\nResult: {result}\n\n"
            embed = Embed(
                title='✅ RPS Result',
                description=description,
                color=0xFFFFFF,
            )
            await self.message.edit(embed=embed, view=None)
        elif (author_choice['name'] == "가위(Scissors)" and opponent_choice['name'] == "보(Paper)") \
                or (author_choice['name'] == "바위(Rock)" and opponent_choice['name'] == "가위(Scissors)") \
                or (author_choice['name'] == "보(Paper)" and opponent_choice['name'] == "바위(Rock)"):
            result = f"{self.challenger.mention} is Winner!"
            description = f"{self.challenger.name}: {author_choice['emoji']}{author_choice['name']}\n" \
                          f"{self.opponent.name}: {opponent_choice['emoji']}{opponent_choice['name']}\n\nResult: {result}\n\n"
            await save_rps_tokens(self.ctx, self.challenger, self.opponent, self.amount, description)
        else:
            result = f"{self.opponent.mention} is Winner!"
            description = f"{self.challenger.name}: {author_choice['emoji']}{author_choice['name']}\n" \
                          f"{self.opponent.name}: {opponent_choice['emoji']}{opponent_choice['name']}\n\nResult: {result}\n\n"
            await save_rps_tokens(self.ctx, self.opponent, self.challenger, self.amount, description)

        self.stop()  # View를 중지하고 버튼을 비활성화

    @discord.ui.button(label="✊ 바위(Rock)", style=discord.ButtonStyle.blurple)
    async def choose_rock(self, button, interaction):
        await self.handle_choice(interaction, "바위(Rock)")

    @discord.ui.button(label="🖐️ 보(Paper)", style=discord.ButtonStyle.green)
    async def choose_paper(self, button, interaction):
        await self.handle_choice(interaction, "보(Paper)")

    @discord.ui.button(label="✌️가위(Scissors)", style=discord.ButtonStyle.red)
    async def choose_scissors(self, button, interaction):
        await self.handle_choice(interaction, "가위(Scissors)")

    async def handle_choice(self, interaction, choice):
        user = interaction.user
        if user != self.challenger and user != self.opponent:
            return

        if user == self.challenger:
            if self.author_choice:
                return
            self.author_choice = choice
        elif user == self.opponent:
            if self.opponent_choice:
                return
            self.opponent_choice = choice

        await interaction.response.send_message(
            f"당신은 {choice}를 선택하셨습니다. 상대방의 선택을 기다려주세요.\n\nYou have selected {choice}. Please wait for opponent choice.",
            ephemeral=True)
        if self.author_choice and self.opponent_choice:
            await self.resolve_game()


class RPSGame2(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_played_date = {}  # user_id를 키로 하고 마지막으로 게임을 한 날짜를 값으로 가지는 딕셔너리

    @commands.command()
    async def rps2(self, ctx, opponent: discord.Member, amount: int):
        embed = Embed(
            title='Game Error',
            description=f"❌ 수동 RPS 게임은 당분간 중단됩니다.\n"
                        f"자동 RPS 게임으로 진행해주세요.\n\n"
                        f"❌ Manual RPS games will be suspended for a while.\n"
                        f"Please proceed with the automatic RPS game.",
            color=0xff0000,
        )
        await ctx.reply(embed=embed, mention_author=True)
        return

        # gameroom_channel_id 채널에서는 제한 없이 게임 가능
        if ctx.channel.id != int(gameroom_channel_id):
            # 해당 유저가 마지막으로 게임을 한 날짜 가져오기
            last_date = self.last_played_date.get(ctx.author.id)

            # 유저가 오늘 이미 게임을 한 경우 에러 메시지 보내기
            if last_date and last_date == datetime.utcnow().date():
                embed = Embed(
                    title='Game Error',
                    description=f"❌ 이 채널에서는 하루에 한 번만 게임을 할 수 있습니다.\n<#{gameroom_channel_id}>에서는 제한없이 가능합니다.\n\n"
                                f"❌ You can only play once a day in this channel.\nYou can play without limits in <#{gameroom_channel_id}>.",
                    color=0xff0000,
                )
                await ctx.reply(embed=embed, mention_author=True)
                return

        if ctx.author.id == opponent.id:
            embed = Embed(
                title='Game Error',
                description="❌ 자신과는 게임을 진행할 수 없습니다.\n\n❌ You can't play with yourself.",
                color=0xff0000,
            )
            await ctx.reply(embed=embed, mention_author=True)
            return

        if abs(amount) > 20:
            embed = Embed(
                title='Game Error',
                description=f"❌ 최대 20개의 토큰만 가능합니다.\n\n"
                            f"❌ You can only have a maximum of 20 tokens.",
                color=0xff0000,
            )
            await ctx.reply(embed=embed, mention_author=True)
            return

        connection = db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                select tokens
                from user_tokens
                where user_id = %s
            """, ctx.author.id)
            user = cursor.fetchone()
            if not user:
                user_tokens = 0
            else:
                user_tokens = int(user['tokens'])

            if abs(amount) > user_tokens:
                embed = Embed(
                    title='Insufficient Tokens',
                    description="❌ 보유한 토큰이 부족합니다. \n\n❌ Token holding quantity is insufficient.",
                    color=0xff0000,
                )
                await ctx.reply(embed=embed, mention_author=True)
                return

            cursor.execute("""
                select tokens
                from user_tokens
                where user_id = %s
            """, opponent.id)
            user = cursor.fetchone()
            if not user:
                user_tokens = 0
            else:
                user_tokens = int(user['tokens'])

            if abs(amount) > user_tokens:
                embed = Embed(
                    title='Insufficient Tokens',
                    description="❌ 상대방이 보유한 토큰이 부족합니다. \n\n❌ Opponent does not have enough tokens.",
                    color=0xff0000,
                )
                await ctx.reply(embed=embed, mention_author=True)
                return

            game_view = RPSGame2View(ctx, ctx.author, opponent, amount)
            await game_view.send_initial_message(ctx)

            if ctx.channel.id != int(gameroom_channel_id):
                self.last_played_date[ctx.author.id] = datetime.utcnow().date()
        except Exception as e:
            logger.error(f'rps error: {e}')
            connection.rollback()
        finally:
            cursor.close()
            connection.close()


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return


bot.add_cog(RPSGame(bot))
bot.add_cog(RPSGame2(bot))
bot.run(bot_token)
