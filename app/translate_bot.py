import os
import discord
import logging
import pymysql
import langid
import deepl
from discord import Member, Embed
from discord.ui import View, button
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB
from discord.ext import commands
from discord.interactions import Interaction
from dotenv import load_dotenv


load_dotenv()

bot_token = os.getenv("SEARCHFI_TRANSLATE_BOT_TOKEN")
command_flag = os.getenv("SEARCHFI_BOT_FLAG")
bot_log_folder = os.getenv("BOT_LOG_FOLDER")
guild_ids = list(map(int, os.getenv('GUILD_ID').split(',')))
local_server = int(os.getenv('SELF_GUILD_ID'))
local_db_file_path = os.getenv('LOCAL_DB_FILE_PATH')
local_db_file_name = os.getenv('LOCAL_DB_FILE_NAME')
deepl_api_key = os.getenv("DEEPL_API_KEY")
allowed_channels = list(map(int, os.getenv('TRANSLATE_CHANNEL_LIST').split(',')))

mysql_ip = os.getenv("MYSQL_IP")
mysql_port = os.getenv("MYSQL_PORT")
mysql_id = os.getenv("MYSQL_ID")
mysql_passwd = os.getenv("MYSQL_PASSWD")
mysql_db = os.getenv("MYSQL_DB")


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(filename=f"{bot_log_folder}/translate_bot.log", mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, host, port, user, password, db):
        self.pool = PooledDB(
            creator=pymysql,
            maxconnections=100,
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


##############################
# Core Function
##############################
bulk = {
    "flag": False,
    "func": ""
}


def change_bulk(flag, func):
    global bulk
    bulk = {
        "flag": flag,
        "func": func
    }


def make_embed(embed_info):
    embed = Embed(
        title=embed_info.get('title', ''),
        description=embed_info.get('description', ''),
        color=embed_info.get('color', 0xFFFFFF),
    )
    if embed_info.get('image_url', None):
        embed.set_image(
            url=embed_info.get('image_url')
        )
    embed.set_footer(text="Powered by SearchFi DEV")
    return embed


##############################
# Class
##############################
class TranslateButton(View):
    def __init__(self, db, message_id):
        super().__init__(timeout=None)
        self.db = db
        self.message_id = message_id

    @button(label="Korean", style=discord.ButtonStyle.gray, custom_id="korean_button")
    async def button_kor(self, _, interaction: Interaction):
        connection = db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                select 
                    message_org,
                    message_kor,
                    message_eng,
                    message_chn
                from messages_translate
                where message_id = %s
            """, self.message_id)

            result = cursor.fetchone()

            if result:
                if result["message_kor"]:
                    answer = result["message_kor"]
                else:
                    translator = deepl.Translator(deepl_api_key)
                    prompt_text: str = result["message_org"]
                    answer = translator.translate_text(prompt_text, target_lang="KO")

                    cursor.execute("""
                        update messages_translate set message_kor = %s
                        where message_id = %s
                    """, (answer, self.message_id))
                    connection.commit()

                description = f"[AI Translation]\n\n{answer}"
                await interaction.response.send_message(
                    content=description,
                    ephemeral=True
                )
        except Exception as e:
            connection.rollback()
            logger.error(f'button_kor db error: {e}')
        finally:
            cursor.close()
            connection.close()

    @button(label="English", style=discord.ButtonStyle.gray, custom_id="english_button")
    async def button_eng(self, _, interaction: Interaction):
        connection = db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                select 
                    message_org,
                    message_kor,
                    message_eng,
                    message_chn
                from messages_translate
                where message_id = %s
            """, self.message_id)

            result = cursor.fetchone()

            if result:
                if result["message_eng"]:
                    answer = result["message_eng"]
                else:
                    translator = deepl.Translator(deepl_api_key)
                    prompt_text: str = result["message_org"]
                    answer = translator.translate_text(prompt_text, target_lang="EN-US")

                    cursor.execute("""
                        update messages_translate set message_eng = %s
                        where message_id = %s
                    """, (answer, self.message_id))
                    connection.commit()

                description = f"[AI Translation]\n\n{answer}"
                await interaction.response.send_message(
                    content=description,
                    ephemeral=True
                )
        except Exception as e:
            connection.rollback()
            logger.error(f'button_eng db error: {e}')
        finally:
            cursor.close()
            connection.close()

    @button(label="Chinese", style=discord.ButtonStyle.gray, custom_id="chinese_button")
    async def button_chn(self, _, interaction: Interaction):
        connection = db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                select 
                    message_org,
                    message_kor,
                    message_eng,
                    message_chn
                from messages_translate
                where message_id = %s
            """, self.message_id)

            result = cursor.fetchone()

            if result:
                if result["message_chn"]:
                    answer = result["message_chn"]
                else:
                    translator = deepl.Translator(deepl_api_key)
                    prompt_text: str = result["message_org"]
                    answer = translator.translate_text(prompt_text, target_lang="ZH")

                    cursor.execute("""
                        update messages_translate set message_chn = %s
                        where message_id = %s
                    """, (answer, self.message_id))
                    connection.commit()

                description = f"[AI Translation]\n\n{answer}"
                await interaction.response.send_message(
                    content=description,
                    ephemeral=True
                )
        except Exception as e:
            connection.rollback()
            logger.error(f'button_chn db error: {e}')
        finally:
            cursor.close()
            connection.close()


@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return

    if message.channel.id in allowed_channels and len(message.content.strip()) > 0:
        connection = db.get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select id
                    from messages_translate
                    where message_id = %s
                """, message.id)
                result = cursor.fetchone()

                if not result:
                    cursor.execute("""
                        insert into messages_translate(message_id, channel_name, user_id, user_name, message_org)
                        values (%s, %s, %s, %s, %s) 
                    """, (message.id, message.channel.name, message.author.id, message.author, message.content))
                    connection.commit()

                view = TranslateButton(db, message.id)
                # custom_id를 각 버튼에 추가하여 영구적으로 만들기
                for child in view.children:
                    if isinstance(child, discord.ui.Button):
                        child.custom_id = f"{child.label.lower()}_{message.id}"
                await message.channel.send(view=view, reference=message)
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            connection.rollback()
        finally:
            connection.close()


@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')

    connection = db.get_connection()
    try:
        with connection.cursor() as cursor:
            # timestamp 컬럼을 사용하여 최근 30일 내의 메시지만 가져오기
            cursor.execute("""
                SELECT message_id 
                FROM messages_translate 
                WHERE timestamp > DATE_SUB(NOW(), INTERVAL 30 DAY)
            """)
            messages = cursor.fetchall()

            # 각 메시지에 대한 View 등록
            for message in messages:
                message_id = message['message_id']
                view = TranslateButton(db, message_id)
                # 각 버튼에 custom_id 설정
                for child in view.children:
                    if isinstance(child, discord.ui.Button):
                        child.custom_id = f"{child.label.lower()}_{message_id}"
                bot.add_view(view)

            logger.info(f"Registered {len(messages)} persistent views for translation buttons")
    except Exception as e:
        logger.error(f"Error registering persistent views: {e}")
    finally:
        connection.close()


bot.run(bot_token)
