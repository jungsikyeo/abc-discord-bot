import os
import discord
import pandas as pd
import logging
import time
import pymysql
from discord import Embed
from discord.ext import commands, tasks
from dotenv import load_dotenv
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB

load_dotenv()

bot_token = os.getenv("SEARCHFI_BOT_TOKEN")
command_flag = os.getenv("SEARCHFI_BOT_FLAG")
ama_vc_channel_id = int(os.getenv("AMA_VC_CHANNEL_ID"))
ama_text_channel_id = int(os.getenv("AMA_TEXT_CHANNEL_ID"))
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
        logging.FileHandler(filename=f"{bot_log_folder}/ama_bot.log", mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

message_counts = {}
message_all_counts = {}
voice_join_counts = {}
voice_leave_counts = {}
voice_channel_time_spent = {}
voice_channel_join_times = {}
ama_role_id = None
ama_in_progress = False
snapshots = []


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


@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def start_ama(ctx, role_id: int):
    global ama_role_id, ama_in_progress
    if ama_in_progress:
        embed = Embed(title="Error",
                      description=f"❌ An AMA session is already in progress.\n\n"
                                  f"❌ AMA 세션이 이미 진행 중입니다.",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        return

    role = discord.utils.get(ctx.guild.roles, id=role_id)
    if role is None:
        embed = Embed(title="Error",
                      description=f"❌ No role found with ID: {role_id}. Please provide a valid role ID.\n\n"
                                  f"❌ {role_id} role을 찾을 수 없습니다. 올바른 role ID를 입력하십시오.",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        return

    try:
        ama_role_id = role_id
        snapshots.clear()
        message_counts.clear()
        message_all_counts.clear()
        voice_join_counts.clear()
        voice_leave_counts.clear()
        voice_channel_time_spent.clear()
        voice_channel_join_times.clear()
        capture_loop.start(ctx)
        # 현재 AMA 채널의 사용자 체크
        voice_channel = bot.get_channel(ama_vc_channel_id)
        current_members = voice_channel.members
        current_time = time.time()
        for member in current_members:
            if not member.bot:  # 봇 제외
                voice_join_counts[member.id] = 1
                voice_channel_join_times[member.id] = current_time  # 입장 시간 설정
        ama_in_progress = True
        embed = Embed(title="Success",
                      description=f"✅ AMA session has started!\n\n"
                                  f"✅ AMA 세션이 시작되었습니다!",
                      color=0x37e37b)
        await ctx.reply(embed=embed, mention_author=True)
    except Exception as e:
        embed = Embed(title="Error",
                      description=f"An error occurred: {str(e)}",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        logger.error(f"An error occurred: {str(e)}")


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def end_ama(ctx):
    global ama_role_id, ama_in_progress
    if not ama_in_progress:
        embed = Embed(title="Error",
                      description=f"❌ No AMA session is currently in progress.\n\n"
                                  f"❌ 현재 진행 중인 AMA 세션이 없습니다.",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        return
    try:
        capture_loop.cancel()
        await capture_final_snapshot(ctx)

        members_to_assign_role = [ctx.guild.get_member(member_id) for member_id in message_counts.keys()]
        await assign_roles(ctx, ama_role_id, members_to_assign_role)

        role_name = discord.utils.get(ctx.guild.roles, id=ama_role_id).name
        await create_and_upload_excel(ctx, snapshots, role_name)

        # 데이터베이스에 데이터 저장
        db_data = []
        for member_id in voice_join_counts:
            total_messages = message_all_counts.get(member_id, 0)
            valid_messages = message_counts.get(member_id, 0)  # 유효한 메시지 수를 여기에 입력하세요
            total_joins = voice_join_counts.get(member_id, 0)
            total_leaves = voice_leave_counts.get(member_id, 0)
            time_spent = int(voice_channel_time_spent.get(member_id, 0))  # 밀리초를 초로 변환

            db_data.append((
                str(ama_role_id), role_name, str(member_id),
                total_messages, valid_messages, total_joins, total_leaves, time_spent
            ))
        # 데이터베이스에 데이터 저장
        await save_data_to_db(ctx, db_data)

        ama_in_progress = False

        embed = Embed(title="Success",
                      description=f"✅ AMA session has ended!\n\n"
                                  f"✅ AMA 세션이 종료되었습니다!",
                      color=0x37e37b)
        await ctx.reply(embed=embed, mention_author=True)

    except Exception as e:
        embed = Embed(title="Error",
                      description=f"An error occurred: {str(e)}",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        logger.error(f"An error occurred: {str(e)}")


async def save_data_to_db(ctx, db_data):
    connection = db.get_connection()
    cursor = connection.cursor()
    try:
        for data in db_data:
            cursor.execute("""
                INSERT INTO ama_users_summary (
                    role_id,
                    role_name,
                    user_id,
                    total_messages,
                    valid_messages,
                    total_joins,
                    total_leaves,
                    time_spent
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, data)

        connection.commit()

        embed = Embed(
            title='DB Save Complete',
            description="DB Save Complete!\n"
                        "Please AMA Summary by User: `!ama_info \"<AMA Role name>\" <User Tag>`",
            color=0xFFFFFF,
        )

        await ctx.reply(embed=embed, mention_author=True)
    except Exception as e:
        logger.error(f'DB error: {e}')
        connection.rollback()
    finally:
        cursor.close()
        connection.close()


@bot.event
async def on_message(message):
    if message.channel.id == ama_text_channel_id and not message.author.bot:
        user_id = message.author.id
        if user_id in message_counts:
            message_counts[user_id] += 1
        else:
            message_counts[user_id] = 1

        if user_id in message_all_counts:
            message_all_counts[user_id] += 1
        else:
            message_all_counts[user_id] = 1
    await bot.process_commands(message)


@tasks.loop(minutes=10)
async def capture_loop(ctx):
    try:
        channel = bot.get_channel(ama_vc_channel_id)
        members = [member for member in channel.members if not member.bot]
        now = pd.Timestamp.now()
        snapshot = {"Timestamp": now}
        for member in members:
            msg_count = message_counts.get(member.id, 0)
            snapshot[member.name] = msg_count
        logger.info(snapshot)
        snapshots.append(snapshot)

        embed = Embed(title="Success",
                      description=f"✅ Snapshot `{now}` has been created.\n\n"
                                  f"✅ `{now}` 스냅샷이 생성되었습니다.",
                      color=0x37e37b)
        await ctx.reply(embed=embed, mention_author=True)
    except Exception as e:
        embed = Embed(title="Error",
                      description=f"An error occurred: {str(e)}",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        logger.error(f"An error occurred: {str(e)}")


async def capture_final_snapshot(ctx):
    try:
        channel = bot.get_channel(ama_vc_channel_id)
        members = [member for member in channel.members if not member.bot]
        now = pd.Timestamp.now()
        current_time = time.time()
        snapshot = {"Timestamp": now}
        for member in members:
            msg_count = message_counts.get(member.id, 0)
            join_time = voice_channel_join_times[member.id]
            time_spent = current_time - join_time
            voice_channel_time_spent[member.id] = voice_channel_time_spent.get(member.id, 0) + time_spent
            snapshot[member.name] = msg_count
        logger.info(snapshot)
        snapshots.append(snapshot)

        embed = Embed(title="Success",
                      description=f"✅ Snapshot `{now}` has been created.\n"
                                  f"Soon a role will be assigned and an Excel file will be created.\n"
                                  f"Please wait a moment.\n\n"
                                  f"✅ `{now}` 스냅샷이 생성되었습니다.\n"
                                  f"곧 롤이 부여되고, 엑셀파일이 생성됩니다.\n"
                                  f"잠시만 기다려주세요.",
                      color=0x37e37b)
        await ctx.reply(embed=embed, mention_author=True)
    except Exception as e:
        embed = Embed(title="Error",
                      description=f"An error occurred: {str(e)}",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        logger.error(f"An error occurred: {str(e)}")


@bot.event
async def on_voice_state_update(member, before, after):
    current_time = time.time()

    # 사용자가 음성 채널에 들어왔는지 확인
    if before.channel is None and after.channel is not None and after.channel.id == ama_vc_channel_id:
        if member.id in voice_join_counts:
            voice_join_counts[member.id] += 1
        else:
            voice_join_counts[member.id] = 1

        # 사용자가 채널에 들어온 시간 기록
        voice_channel_join_times[member.id] = current_time

    # 사용자가 음성 채널에서 나갔는지 확인
    if before.channel is not None and before.channel.id == ama_vc_channel_id and after.channel is None:
        if member.id in voice_leave_counts:
            voice_leave_counts[member.id] += 1
        else:
            voice_leave_counts[member.id] = 1

        # 사용자가 채널에서 나간 시간 기록 및 머무른 시간 계산
        if member.id in voice_channel_join_times:
            join_time = voice_channel_join_times[member.id]
            time_spent = current_time - join_time
            voice_channel_time_spent[member.id] = voice_channel_time_spent.get(member.id, 0) + time_spent
            # 사용자가 나간 후, join 시간 정보 삭제
            del voice_channel_join_times[member.id]

        # AMA 중에 음성 채널을 떠나면 해당 사용자의 message_counts를 제거
        if member.id in message_counts:
            del message_counts[member.id]


async def assign_roles(ctx, role_id, members):
    role = discord.utils.get(ctx.guild.roles, id=role_id)
    for member in members:
        try:
            await member.add_roles(role)
        except discord.Forbidden:
            embed = Embed(title="Error",
                          description=f"Failed to assign role to {member.name}. Check the bot's permissions.",
                          color=0xff0000)
            await ctx.reply(embed=embed, mention_author=True)
            logger.warning(f"Failed to assign role to {member.name}. Check the bot's permissions.")
        except discord.HTTPException as e:
            embed = Embed(title="Error",
                          description=f"HTTP exception while assigning role to {member.name}: {str(e)}",
                          color=0xff0000)
            await ctx.reply(embed=embed, mention_author=True)
            logger.warning(f"Failed to assign role to {member.name}. Check the bot's permissions.")
            logger.error(f"HTTP exception while assigning role to {member.name}: {str(e)}")


async def create_and_upload_excel(ctx, snapshots, role_name):
    file_name = f'ama_summary_{role_name}.xlsx'
    with pd.ExcelWriter(file_name, engine='xlsxwriter') as writer:
        # 스냅샷 데이터를 엑셀에 기록
        for snapshot in snapshots:
            timestamp = snapshot["Timestamp"]
            formatted_timestamp = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
            df = pd.DataFrame(list(snapshot.items())[1:], columns=['Member', 'Message_Count'])
            df.to_excel(writer, sheet_name=f'{formatted_timestamp}', index=False)

        # 사용자별 통계 데이터를 포함하는 새 데이터 프레임 생성
        data = []
        for member_id in message_all_counts:
            try:
                member = ctx.guild.get_member(member_id)
                if member:  # 사용자가 여전히 서버에 있는 경우
                    member_name = member.display_name  # 멤버의 디스플레이 이름 가져오기
                else:  # 사용자가 서버를 떠난 경우
                    member_name = str(member_id)  # 멤버의 ID를 문자열로 사용
                    logger.warning(f"Member with ID {member_id} not found. They might have left the server.")
            except Exception as e:  # 다른 예외 처리
                member_name = "Unknown"
                logger.error(f"An error occurred while getting member info: {str(e)}")

            total_messages = message_all_counts.get(member_id, 0)
            total_joins = voice_join_counts.get(member_id, 0)
            total_leaves = voice_leave_counts.get(member_id, 0)
            total_time_spent = int(voice_channel_time_spent.get(member_id, 0))  # 총 시간은 초 단위로 계산됩니다.

            data.append({
                'Member_ID': member_id,
                'Member_Name': member_name,
                'Total_Messages': total_messages,
                'Total_Joins': total_joins,
                'Total_Leaves': total_leaves,
                'Total_Time_Spent_in_VC_(seconds)': total_time_spent,  # 초 단위의 시간
            })

        df_summary = pd.DataFrame(data)
        df_summary.to_excel(writer, sheet_name='Summary', index=False)  # 'Summary' 시트에 데이터 기록

    try:
        with open(file_name, 'rb') as f:
            await ctx.reply(file=discord.File(f), mention_author=True)
        os.remove(file_name)  # 파일 사용이 완료된 후 파일 삭제
    except discord.HTTPException as e:
        embed = Embed(title="Error",
                      description=f"Failed to upload the file: {str(e)}",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        logger.error(f"Failed to upload the file: {str(e)}")
    except FileNotFoundError as e:
        embed = Embed(title="Error",
                      description=f"Failed to delete the file. It might have been already deleted or not found: {str(e)}",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        logger.error(f"Failed to delete the file: {str(e)}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    else:
        logger.error(f"An error occurred: {str(error)}")


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def ama_info(ctx, role_name: str, member: discord.Member):
    try:
        # 데이터베이스에서 사용자 정보 조회
        user_summary = await get_user_summary_from_db(role_name, member.id)
        if user_summary:
            # 시간을 분과 초로 변환
            total_seconds = user_summary['time_spent']
            minutes, seconds = divmod(total_seconds, 60)
            if minutes > 0:
                time_spent_str = f"`{minutes}` minutes `{seconds}` seconds"
            else:
                time_spent_str = f"`{seconds}` seconds"

            embed = Embed(title=f"{role_name} Summary for {member.display_name}",
                          description=f"- Total Messages: `{user_summary['total_messages']}`\n"
                                      f"- Valid Messages: `{user_summary['valid_messages']}`\n"
                                      f"- AMA VC Joins: `{user_summary['total_joins']}`\n"
                                      f"- AMA VC Leaves: `{user_summary['total_leaves']}`\n"
                                      f"- Time Spent: {time_spent_str}",
                          color=0x37e37b)
        else:
            embed = Embed(title="No Data Found",
                          description=f"No summary data found for {member.display_name} in {role_name}.",
                          color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
    except Exception as e:
        embed = Embed(title="Error",
                      description=f"An error occurred: {str(e)}",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        logger.error(f"An error occurred: {str(e)}")


async def get_user_summary_from_db(role_name, user_id):
    connection = db.get_connection()
    cursor = connection.cursor()
    user_summary = None
    try:
        # 사용자 요약 정보 조회
        cursor.execute("""
            SELECT * FROM ama_users_summary
            WHERE role_name = %s AND user_id = %s
            """, (role_name, str(user_id)))
        result = cursor.fetchone()
        if result:
            user_summary = {
                'total_messages': result['total_messages'],
                'valid_messages': result['valid_messages'],
                'total_joins': result['total_joins'],
                'total_leaves': result['total_leaves'],
                'time_spent': result['time_spent']
            }
    except Exception as e:
        logger.error(f'DB error: {e}')
    finally:
        cursor.close()
        connection.close()
    return user_summary










import json

# 주어진 JSON 데이터
data = {
"kingrk": 9,
"fallenleaf777": 9,
"papason": 3,
"justinjang": 14,
"jinee.super": 27,
"masque9807": 23,
"972_": 1,
"eth_apple": 14,
"cherrycoco": 12,
"wonseok1817": 4,
".fashionpolice": 13,
"navi.eth": 45,
"insanelee": 13,
"person.nice": 39,
"darkk3164": 12,
"top6735": 23,
"richardsong": 1,
"hanhsiang": 3,
"zoozoo_": 9,
"ohtani6861": 11,
"pipimao": 3,
"sanghoking": 33,
"marie5931": 72,
"kitty_0u0_cherry": 34,
"sommie9417": 22,
"t0xzhisheng": 1,
"일론마스크": 24,
"mr.kitkit": 41,
"nicchun": 36,
"aby123": 23,
"potat0x": 19,
"lina7328": 25,
"debss0365": 47,
"yunhyeok": 7,
"yesakita": 6,
"hunter_fka": 13,
"0xnaldo": 34,
"moon6800": 18,
"im___winter": 59,
"han0202": 5,
"roseblackpink": 10,
"harryc93": 7,
"effzee": 7,
"chevan.eth": 0,
"royalfamily_eth": 5,
"rangrang_.anotherworld": 35,
"smart6609": 0,
"poshbabe": 80,
"aha.o": 63,
"cyber_shu": 0,
"junel": 26,
"jjjjjuuuuu": 7,
"itsjonr": 2,
"eunhopapa": 2,
"jambivert": 22,
"haverland75": 16,
"blueminions": 1,
"porsche911": 11,
"kolupu": 7,
"mackenzzisteele1839": 80,
"hillspearl": 7,
"mathzin.eth": 15,
"presh1210": 44,
"kimmykim": 3,
"slime5111": 20,
"joshua_or_josh": 13,
"brc_peter": 0,
"ariel35.": 16,
"tfortabasco": 0,
"king_dele07": 29,
"irene_ine": 16,
"rockxxx": 8,
"kimsw": 26,
"liliwithlove": 16,
"lovemushroom": 80,
"aaliyah0030": 14,
"hhisnothing": 14,
"opyaansradiance": 16,
"starboycrypto1": 0,
"innocentzero": 5,
"revjoy": 0,
"eraserranora": 6,
"chrisnico": 6,
"vegeta_.sama": 13,
"lys5566": 17,
"duubemmm": 25,
"payne21": 22,
"jokergeee": 0,
"shivam051": 6,
"maimai4675": 1,
"tomtom9169": 6,
"daram.eth": 3,
"nicolepaquin": 0,
".bedas": 6,
"treasure3818": 40,
"justinagarrison": 0,
"ibtissamkaraka": 0,
"reust": 15,
"cannongrayson": 0,
"dog.player": 45,
"wildchest": 11,
"SuttonJack": 0,
"SchulerAndreas": 0,
"ezenku": 45,
"ㅇEricaㅇ": 0,
"julylove": 0,
"야옹냐옹": 0,
"cornelaci": 25,
"GODSENT": 0,
"마이프레셔스": 0,
"oxygen222": 28,
"머핀맨": 0,
"조아핑": 0,
"hayul_papa": 9,
"roonygoal": 0,
"Anna0315": 0,
"애니오타쿠": 0,
"십자가": 0,
"구구콘": 0,
".blackswan": 2,
"팔이클하상": 0,
"칠면죠": 0,
"육개장": 0,
"오지명": 0,
"사랑꾼": 0,
"삼삼해": 0,
"chung_11": 9,
"memall": 0,
"lemam": 0,
"gy_1212": 2,
"seo._.o": 47,
"kimchiii0319": 25,
"lupin3th": 16,
"tammy1728": 22,
"0xjiahao": 0,
"abigeal.": 5,
"dashy5667": 0,
"10nft.cat": 5,
"hsientreepay": 3,
"mrborger1": 1,
"Bad influence😈": 13,
"1_1pai": 5,
"tbg0069": 10,
"blaqoo": 0,
"jatio": 49,
"antone.": 0,
"hemdy_classic": 11,
"boyjay": 4,
"darksaber_eth": 2,
"_ghjkl": 11,
"telles_dx": 20,
"asunawon": 8,
"d10.eth": 5,
"kenji9359": 39,
"Stars E 💙": 19,
"Tunny": 9,
"agent_pet": 5,
"henry5604": 13,
"chiyoyoyo": 12,
"doosingod": 16,
"sadcat9698": 8,
"charlesjr9439": 23,
"hanny": 8,
"jj85_3920": 11,
"juice": 6,
"benben4751": 2,
"songsong6059": 5,
"gavinner66": 6,
"melody.eth": 9,
"jake4980": 4,
"jackykao15": 26,
"supra.btc": 10,
"moonkz": 0,
"GOLDIE🥀👻": 4,
"jonggggg": 9,
"xpsalmx": 8,
"x_ayomide": 14,
"stan4326": 4,
"gguang_": 9,
"dmddo77": 7,
"𝐀𝐑𝐈𝐄𝐒𝐐𝐔𝐄𝐄𝐍 🎭": 11,
"krister8516": 2,
"rita2433": 1,
"supercatsol": 1,
"kevtw": 4,
"xstchael": 7,
"mrx2778": 0,
"preshous": 5,
"halosunny": 1,
"boyuboyu": 1,
"konstrvct": 0,
"pablomannyotm": 0,
"0xblonded": 0,
"thewealthhunter": 2,
"temie7012": 3,
"itsnothing.": 0,
"jay4orce": 3,
"halima7406": 3,
"darkryder01": 0,
"carrotchan": 1,
"0xdavidmaxeth": 0
}

@bot.command()
async def extract_ids(ctx):
    guild = ctx.guild
    result = {}

    for username, message_count in data.items():
        if message_count > 0:
            member = discord.utils.get(guild.members, name=username)
            if member:
                result[username] = member.id
            else:
                result[username] = "no search"

    # 결과를 JSON 파일로 저장
    with open("extracted_ids.json", "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)

    await ctx.send("Extracted IDs have been saved to `extracted_ids.json`.", file=discord.File("extracted_ids.json"))


bot.run(bot_token)
