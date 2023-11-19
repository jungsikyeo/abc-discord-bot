import discord
import os
import logging
import pymysql
import datetime
import random
import asyncio
import pytz
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from dotenv import load_dotenv
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB
from discord.ext import commands
from discord import Embed, Button, ButtonStyle
from discord.ui import View
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

searchfi_amount = 110
lm_amount = 165
min_win = 1
max_win = 5
win_limit = 4

exclude_role_list = list(map(int, os.getenv('C2E_EXCLUDE_ROLE_LIST').split(',')))
enabled_channel_list = list(map(int, os.getenv('C2E_ENABLED_CHANNEL_LIST').split(',')))


# 한국 시간대 기준 정오(낮 12시) 시간 구하기
def get_noon_kst():
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz)
    noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
    return noon.timestamp() if now >= noon else (noon - timedelta(days=1)).timestamp()


# 기준 시간으로부터 최대 지속 시간 내에서 무작위 시간 생성
def random_time(base, max_duration):
    return base + random.randint(0, max_duration)


async def weekly_top_reset():
    # 1주일(604800초) 대기
    await asyncio.sleep(604800)

    # 현재 시간을 기준으로 새로운 주간 탑 상품 시간 설정
    now = datetime.now().timestamp()
    global weekly_top
    weekly_top = [
        random_time(now, 204800),
        random_time(now + 204800, 200000),
        random_time(now + 404800, 200000)
    ]

    # 로그 기록
    logger.info(f"Weekly top reset at {datetime.now()}. Next times: {weekly_top}")

    # 함수를 다시 비동기적으로 호출하여 주기적으로 재설정 계속
    asyncio.create_task(weekly_top_reset())


@bot.event
async def on_ready():
    # 봇이 준비되었을 때 실행할 코드
    logger.info(f"{bot.user} is now online!")

    # 데이터베이스 연결
    connection = db.get_connection()
    cursor = connection.cursor()

    try:
        # SEARCHFI 토큰 초기화 및 스케줄링
        next_reset = get_noon_kst() + 1000
        cursor.execute("""
            INSERT INTO c2e_token_tracking (type, reset_at, still_available) 
            VALUES (%s, %s, %s) 
            ON DUPLICATE KEY UPDATE reset_at = VALUES(reset_at)
        """, ("searchfi", next_reset, searchfi_amount))

        # 커밋
        connection.commit()

        cursor.execute("""
            SELECT reset_at, still_available FROM c2e_token_tracking WHERE type = %s
        """, ("searchfi",))
        searchfi_data = cursor.fetchone()

        print(f"searchfi {searchfi_data}")

        asyncio.create_task(schedule_reset("searchfi", False))

    except Exception as e:
        logger.error(f'Error in on_ready: {e}')
        connection.rollback()
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
        return

    # 메시지가 허용된 채널 중 하나에서 왔는지 확인
    if message.channel.id not in enabled_channel_list:
        return

    # tokensData와 winnerUsers를 확인하여 토큰 지급 여부 결정
    type1 = "searchfi"
    global winner_users, tokens_data
    current_timestamp = datetime.now().timestamp()
    print(datetime.fromtimestamp(current_timestamp), datetime.fromtimestamp(tokens_data[type1]))
    if tokens_data.get(type1) and current_timestamp > tokens_data[type1]:
        if not winner_users.get(message.author.id) or winner_users[message.author.id] < win_limit:
            # searchfi 토큰 지급
            await give_points(message, type1)
            winner_users[message.author.id] = winner_users.get(message.author.id, 0) + 1
            tokens_data[type1] = None  # 토큰 지급 후 데이터 업데이트

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
            INSERT INTO user_tokens_test (user_id, tokens) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE tokens = tokens + VALUES(tokens)
        """, (message.author.id, token_amount))

        # 커밋
        connection.commit()

        # 메시지 임베드 생성
        embed = Embed(
            # title="Congratulations 🎉 🎉",
            # description=f"You just won **{token_amount}** {token_type} tokens!",
            # description=f"You just won **{token_amount}** {token_type} tokens!",
            title="Congratulations 🎉 🎉 (Sorry.. Test :joy: )",
            description=f"You just won **{token_amount}** test tokens!",
            color=0x9da1ef
        )
        embed.set_image(url="https://cdn.discordapp.com/attachments/955428076651679846/1091499808960811008/IMG_0809.gif")

        # 메시지 전송
        await message.channel.send(embed=embed)
    except Exception as e:
        connection.rollback()
        logger.error(f'Error in give_points: {e}')
    finally:
        cursor.close()
        connection.close()


# 암호화 키 설정
key = bytes.fromhex(os.getenv('ENCRYPTION_KEY_HEX'))
iv = bytes.fromhex(os.getenv('ENCRYPTION_IV_HEX'))


# 데이터 암호화
def encrypt_data(user_id, amount):
    backend = default_backend()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
    encryptor = cipher.encryptor()
    data = f'{user_id},{amount},{int(datetime.now().timestamp())}'
    encrypted = encryptor.update(data.encode('utf-8')) + encryptor.finalize()
    return encrypted.hex()


# 데이터 복호화
def decrypt_data(data):
    backend = default_backend()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(bytes.fromhex(data)) + decryptor.finalize()
    return dict(zip(['u', 't'], decrypted.decode('utf-8').split(',')))


async def give_weekly_top_prize(message):
    tokens = 100  # 예시 토큰 수량
    encrypted_data = encrypt_data(message.author.id, tokens)

    # 임베드 메시지 생성
    embed = Embed(
        title="Congratulations 🎉 🎉",
        description=f"You just won **{tokens}** LM tokens! Submit your wallet now to receive your prize",
        color=0x9da1ef
    )
    embed.set_image(url="https://cdn.discordapp.com/attachments/955428076651679846/1091499809317335212/IMG_0810.gif")

    # 버튼 컴포넌트 생성
    button = Button(label="Submit Wallet", style=ButtonStyle.primary, custom_id=f'gw-{encrypted_data}')
    view = View()
    view.add_item(button)

    # 메시지와 함께 임베드와 버튼 전송
    await message.channel.send(embed=embed, view=view)


async def schedule_reset(token_type, light):
    # 토큰 정보 가져오기
    connection = db.get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("""
            SELECT reset_at, still_available FROM c2e_token_tracking WHERE type = %s
        """, token_type)
        searchfi_data = cursor.fetchone()
        next_reset = int(searchfi_data['reset_at']) + 1000  # 다음 리셋 시간 계산

        # 데이터베이스에서 토큰 리셋 시간 업데이트
        cursor.execute("""
            UPDATE c2e_token_tracking SET reset_at = %s, still_available = %s 
            WHERE type = %s
        """, (next_reset, searchfi_amount if token_type == "searchfi" else lm_amount, token_type))

        connection.commit()

        # 토큰 데이터 리셋
        global winner_users, tokens_data
        tokens_data[token_type] = None
        winner_users = {}

        await schedule_give(token_type)

        # 다음 리셋까지 대기
        print(f"sleep: {next_reset - datetime.now().timestamp()}")
        await asyncio.sleep(next_reset - datetime.now().timestamp())
        # await asyncio.sleep(43200)

        # 다음 리셋 스케줄링
        print(f"resetting tokens at, {datetime.fromtimestamp(next_reset)}, {token_type}")
        asyncio.create_task(schedule_reset(token_type, light))
    except Exception as e:
        connection.rollback()
        logger.error(f'schedule_reset db error: {e}')
    finally:
        cursor.close()
        connection.close()


async def schedule_give(token_type):
    # 토큰 정보 가져오기
    connection = db.get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("""
            SELECT reset_at, still_available FROM c2e_token_tracking WHERE type = %s
        """, token_type)
        tok_info = cursor.fetchone()

        logger.info(f"tokInfo scheduleGive {tok_info}, {token_type}")

        if tok_info and tok_info['still_available'] > 0:
            # 지급 시간 계산
            rate = (tok_info['still_available'] / ((min_win + max_win) / 2)) + 1
            give_points_in = round((int(tok_info['reset_at']) - datetime.now().timestamp()) / rate)
            randomized = round((give_points_in * 0.80) + (random.random() * give_points_in * 0.40))

            logger.info(f"Give points in {int(datetime.now().timestamp()) + (randomized / 1000)} for {token_type}")

            global tokens_data
            tokens_data[token_type] = int(datetime.now().timestamp()) + (randomized / 1000)

    except Exception as e:
        connection.rollback()
        logger.error(f'schedule_give db error: {e}')
    finally:
        cursor.close()
        connection.close()


bot.run(bot_token)