import discord
import os
import logging
import pymysql
import datetime
import random
import asyncio
import pytz
from dotenv import load_dotenv
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB
from discord.ext import commands
from discord import Embed
from discord.ui import View, button, Modal, InputText
from discord.interactions import Interaction
from datetime import datetime, timedelta

load_dotenv()

bot_token = os.getenv("SEARCHFI_BOT_TOKEN")
command_flag = os.getenv("SEARCHFI_BOT_FLAG")
bot_log_folder = os.getenv("BOT_LOG_FOLDER")
mysql_ip = os.getenv("MYSQL_IP")
mysql_port = os.getenv("MYSQL_PORT")
mysql_id = os.getenv("MYSQL_ID")
mysql_passwd = os.getenv("MYSQL_PASSWD")
mysql_db = os.getenv("MYSQL_DB")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(filename=f"{bot_log_folder}/chat_token_bot.log", mode='a'),
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


intents = discord.Intents.all()
bot = commands.Bot(command_prefix=f"{command_flag}", intents=intents)
db = Database(mysql_ip, mysql_port, mysql_id, mysql_passwd, mysql_db)

tokens_data = {}
winner_users = {}
used_verify_lm = []
weekly_top = []

searchfi_amount = 100
min_win = 1
max_win = 5
win_limit = 4

lock_status = True

exclude_role_list = list(map(int, os.getenv('C2E_EXCLUDE_ROLE_LIST').split(',')))
enabled_channel_list = list(map(int, os.getenv('C2E_ENABLED_CHANNEL_LIST').split(',')))

c2e_type = os.getenv("C2E_TYPE")


class TokenSettingsModal(Modal):
    def __init__(self, data):
        super().__init__(title="SF Token Settings")
        self.add_item(InputText(label="Daily Token Limit",
                                placeholder="Enter the daily token limit",
                                value=f"{data.get('daily_token_limit')}"))
        self.add_item(InputText(label="Minimum Tokens per Win",
                                placeholder="Enter the minimum tokens per win",
                                value=f"{data.get('min_win')}"))
        self.add_item(InputText(label="Maximum Tokens per Win",
                                placeholder="Enter the maximum tokens per win",
                                value=f"{data.get('max_win')}"))
        self.add_item(InputText(label="Win Limit per User",
                                placeholder="Enter the win limit per user",
                                value=f"{data.get('win_limit')}"))

    async def callback(self, interaction: Interaction):
        # 데이터베이스 업데이트 로직
        daily_limit = self.children[0].value
        min_tokens = self.children[1].value
        max_tokens = self.children[2].value
        user_limit = self.children[3].value

        connection = db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                UPDATE c2e_token_tracking 
                SET 
                    daily_token_limit = %s,
                    min_win = %s,
                    max_win = %s,
                    win_limit = %s
                WHERE type = %s
            """, (daily_limit, min_tokens, max_tokens, user_limit, c2e_type))
            connection.commit()
        except Exception as e:
            connection.rollback()
            logger.error(f'TokenSettingsModal db error: {e}')
        finally:
            cursor.close()
            connection.close()

        await interaction.response.send_message("SF 토큰 설정이 업데이트되었습니다!\n\n"
                                                "SF Token settings updated successfully!", ephemeral=True)


# 버튼 클래스 정의
class TokenSettingsButton(View):
    def __init__(self, db):
        super().__init__()
        self.db = db

    @button(label="setting", style=discord.ButtonStyle.primary, custom_id="setting_sftoken_button")
    async def button_add_setting(self, _, interaction: Interaction):
        searchfi_data = {}
        connection = db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                SELECT 
                    daily_token_limit,
                    min_win,
                    max_win,
                    win_limit
                FROM c2e_token_tracking
                WHERE type = %s
            """, c2e_type)
            searchfi_data = cursor.fetchone()
        except Exception as e:
            connection.rollback()
            logger.error(f'button_add_setting db error: {e}')
        finally:
            cursor.close()
            connection.close()
        await interaction.response.send_modal(modal=TokenSettingsModal(searchfi_data))


# 한국 시간대 기준 정오(낮 12시) 시간 구하기
def get_noon_kst():
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz)
    noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
    return noon.timestamp() if now >= noon else (noon - timedelta(days=1)).timestamp()


# 기준 시간으로부터 최대 지속 시간 내에서 무작위 시간 생성
def random_time(base, max_duration):
    return base + random.randint(0, max_duration)


@bot.event
async def on_ready():
    # 봇이 준비되었을 때 실행할 코드
    logger.info(f"{bot.user} is now online!")

    # 데이터베이스 연결
    connection = db.get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT reset_at, still_available, daily_token_limit, min_win, max_win, win_limit
            FROM c2e_token_tracking WHERE type = %s
        """, (c2e_type,))
        searchfi_data = cursor.fetchone()

        global searchfi_amount, min_win, max_win, win_limit, lock_status

        # SEARCHFI 토큰 초기화 및 스케줄링
        if not searchfi_data:
            next_reset = get_noon_kst()
            cursor.execute("""
                INSERT INTO c2e_token_tracking (type, reset_at) 
                VALUES (%s, %s) 
            """, (c2e_type, next_reset))

            cursor.execute("""
                SELECT reset_at, still_available, daily_token_limit, min_win, max_win, win_limit
                FROM c2e_token_tracking WHERE type = %s
            """, (c2e_type,))
            searchfi_data = cursor.fetchone()

            searchfi_amount = searchfi_data['still_available']
            min_win = searchfi_data['min_win']
            max_win = searchfi_data['max_win']
            win_limit = searchfi_data['win_limit']

        # 커밋
        connection.commit()

        print(
            f"searchfi ready: {datetime.fromtimestamp(searchfi_data['reset_at'])}, {searchfi_data['still_available']}")

        asyncio.create_task(schedule_reset(c2e_type, False))

        lock_status = False

    except Exception as e:
        logger.error(f'Error in on_ready: {e}')
        connection.rollback()
    finally:
        cursor.close()
        connection.close()


async def schedule_reset(token_type, run_type=True):
    # 토큰 정보 가져오기
    connection = db.get_connection()
    cursor = connection.cursor()
    try:
        global searchfi_amount, min_win, max_win, win_limit
        cursor.execute("""
                SELECT reset_at, still_available, daily_token_limit, min_win, max_win, win_limit
                FROM c2e_token_tracking WHERE type = %s
            """, (c2e_type,))
        searchfi_data = cursor.fetchone()

        searchfi_amount = searchfi_data['daily_token_limit']
        min_win = searchfi_data['min_win']
        max_win = searchfi_data['max_win']
        win_limit = searchfi_data['win_limit']

        if run_type:
            next_reset = int(searchfi_data['reset_at']) + 43200  # 다음 리셋 시간 계산

            # 데이터베이스에서 토큰 리셋 시간 업데이트
            cursor.execute("""
                UPDATE c2e_token_tracking SET reset_at = %s, still_available = %s 
                WHERE type = %s
            """, (next_reset, searchfi_amount, token_type))

            connection.commit()
        else:
            next_reset = int(searchfi_data['reset_at'])

        # 토큰 데이터 리셋
        global winner_users, tokens_data
        tokens_data[token_type] = None
        winner_users = {}

        await schedule_give(token_type)

        # 다음 리셋까지 대기
        print(f"sleep: {next_reset - datetime.now().timestamp()}")
        await asyncio.sleep(next_reset - datetime.now().timestamp())

        # 다음 리셋 스케줄링
        logger.info(f"resetting tokens at, {datetime.fromtimestamp(next_reset)}, {token_type}")
    except Exception as e:
        connection.rollback()
        logger.error(f'schedule_reset db error: {e}')
    finally:
        cursor.close()
        connection.close()
        asyncio.create_task(schedule_reset(token_type))


async def schedule_give(token_type):
    # 토큰 정보 가져오기
    connection = db.get_connection()
    cursor = connection.cursor()
    try:
        # 남은 토큰 수량 확인
        cursor.execute("""
            SELECT reset_at, still_available FROM c2e_token_tracking WHERE type = %s
        """, (token_type,))
        result = cursor.fetchone()
        reset_at = datetime.fromtimestamp(result['reset_at'])
        available = result['still_available']

        # 평균 토큰 지급량 계산
        average_tokens_per_distribution = (min_win + max_win) / 2  # min_win, max_win 개의 평균

        # 남은 시간 계산
        now = datetime.now()
        remaining_seconds = (reset_at - now).total_seconds()

        # 새로운 토큰 지급 주기 계산
        if available > 0:
            new_rate = remaining_seconds / (available / average_tokens_per_distribution)
            random_offset = random.randint(-90, 90)  # -1분 30초 ~ +1분 30초
            next_give_time = now.timestamp() + new_rate + random_offset
        else:
            next_give_time = reset_at.timestamp()  # 토큰이 없으면 다음 리셋 시간으로 설정

        # 토큰 지급 시간 업데이트
        tokens_data[token_type] = next_give_time
    except Exception as e:
        connection.rollback()
        logger.error(f'schedule_give db error: {e}')
    finally:
        cursor.close()
        connection.close()


@bot.event
async def on_message(message):
    # 봇 자신의 메시지는 처리하지 않음
    if message.author.bot:
        return

    # 특정 역할을 가진 사용자의 메시지는 무시
    if any(role.id in exclude_role_list for role in message.author.roles):
        await bot.process_commands(message)
        return

    # 메시지가 허용된 채널 중 하나에서 왔는지 확인
    if message.channel.id not in enabled_channel_list:
        await bot.process_commands(message)
        return

    # tokensData와 winnerUsers를 확인하여 토큰 지급 여부 결정
    type1 = c2e_type
    global winner_users, tokens_data, lock_status
    current_timestamp = datetime.now().timestamp()
    if tokens_data.get(type1):
        print(datetime.fromtimestamp(current_timestamp), datetime.fromtimestamp(tokens_data[type1]))
    if not lock_status and tokens_data.get(type1) and current_timestamp > tokens_data[type1]:
        if not winner_users.get(message.author.id) or winner_users[message.author.id] < win_limit:
            lock_status = True
            # searchfi 토큰 지급
            await give_points(message, type1)
            await schedule_give(type1)
            lock_status = False

    # 명령어 처리를 위해 기본 on_message 핸들러 호출
    await bot.process_commands(message)


async def give_points(message, token_type):
    # 데이터베이스 연결 및 토큰 정보 업데이트
    connection = db.get_connection()
    cursor = connection.cursor()
    try:
        # 해당 토큰 유형의 남은 토큰 양 확인
        cursor.execute("""
            SELECT still_available FROM c2e_token_tracking WHERE type = %s
        """, (token_type,))
        available = cursor.fetchone()['still_available']

        # 랜덤 토큰 양 계산
        rand = random.randint(min_win, max_win)
        token_amount = available if available - rand < min_win else rand

        # 남은 토큰 양 업데이트
        cursor.execute("""
            UPDATE c2e_token_tracking SET still_available = still_available - %s 
            WHERE type = %s
        """, (token_amount, token_type))

        # 사용자 토큰 증가
        cursor.execute("""
            INSERT INTO user_tokens (user_id, tokens) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE tokens = tokens + VALUES(tokens)
        """, (message.author.id, token_amount))

        # 사용자 토큰 부여 로그
        cursor.execute("""
            INSERT INTO c2e_token_logs (
                user_id, tokens, user_name, send_user_id, send_user_name, channel_id, channel_name, action_type
            ) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (message.author.id, token_amount, message.author.name,
              'bot', 'bot', message.channel.id, message.channel.name, 'CHAT'))
        print(f"{message.channel.name} -> {message.author.name} : {token_amount}")

        # 커밋
        connection.commit()

        # 메시지 임베드 생성
        embed = Embed(
            title="Congratulations 🎉 🎉",
            description=f"You just won **{token_amount}** {token_type} tokens!",
            # title="Congratulations 🎉 🎉 (Sorry.. Test :joy: )",
            # description=f"You just won **{token_amount}** test tokens!",
            color=0x9da1ef
        )
        embed.set_image(
            url="https://cdn.discordapp.com/attachments/955428076651679846/1091499808960811008/IMG_0809.gif")

        # 메시지 전송
        await message.reply(embed=embed)
    except Exception as e:
        connection.rollback()
        logger.error(f'Error in give_points: {e}')
    finally:
        cursor.close()
        connection.close()


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def setting_sf_tokens(ctx):
    embed = Embed(title="SF Token Settings", description="아래 버튼으로 SF 토큰을 세팅해주세요.\n\n"
                                                         "Please setting SF Token using the button below.",
                  color=0xFFFFFF)
    view = TokenSettingsButton(db)
    await ctx.reply(embed=embed, view=view, mention_author=True)


bot.run(bot_token)
