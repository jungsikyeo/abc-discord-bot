import datetime
import time
import pymysql
import discord
import requests
import math
from discord.ui import Button, View
from discord.ext import commands
from discord import Embed
from paginator import Paginator, Page, NavigationType
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB
from urllib.parse import quote
import os
from dotenv import load_dotenv

load_dotenv()

bot_token = os.getenv("SEARCHFI_BOT_TOKEN")
mysql_ip = os.getenv("MYSQL_IP")
mysql_port = os.getenv("MYSQL_PORT")
mysql_id = os.getenv("MYSQL_ID")
mysql_passwd = os.getenv("MYSQL_PASSWD")
mysql_db = os.getenv("MYSQL_DB")

discord_client_id = os.getenv("DISCORD_CLIENT_ID")

class UpDownView(View):
    def __init__(self, ctx, embed_message, embed, db, project_id):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.embed_message = embed_message
        self.embed = embed
        self.db = db
        self.project_id = project_id
        self.regUser = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"
        if self.embed_message is not None:
            self.update_message()

    async def on_timeout(self):
        await self.embed_message.edit(view=None)

    def update_message(self):
        self.embed_message.edit(embed=self.embed, view=self)

    @discord.ui.button(label="UP", style=discord.ButtonStyle.green)
    async def up_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        buttonView = ButtonView(self.ctx, self.db, "")
        Queries.merge_recommend(self.db, self.project_id, self.regUser, "UP")
        item = Queries.select_one_project(self.db, self.project_id)
        try:
            avatar_url = await buttonView.get_member_avatar(item['regUser'].split('#')[0], item['regUser'].split('#')[1])
        except Exception as e:
            avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
        item["avatar_url"] = avatar_url
        embed = buttonView.makeEmbed(item)
        await self.embed_message.edit(embed=embed, view=self)

    @discord.ui.button(label="DOWN", style=discord.ButtonStyle.red)
    async def down_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        buttonView = ButtonView(self.ctx, self.db, "")
        Queries.merge_recommend(self.db, self.project_id, self.regUser, "DOWN")
        item = Queries.select_one_project(self.db, self.project_id)
        try:
            avatar_url = await buttonView.get_member_avatar(item['regUser'].split('#')[0], item['regUser'].split('#')[1])
        except Exception as e:
            avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
        item["avatar_url"] = avatar_url
        embed = buttonView.makeEmbed(item)
        await self.embed_message.edit(embed=embed, view=self)

class ButtonView(discord.ui.View):
    def __init__(self, ctx, db, day):
        super().__init__()
        self.ctx = ctx
        self.db = db
        self.day = day
        self.id = ctx.message.author.id
        self.username = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"
        self.desktop = ctx.message.author.desktop_status
        self.mobile = ctx.message.author.mobile_status
    
    async def get_member_avatar(self, member_name: str, member_discriminator: str):
        member = discord.utils.get(self.ctx.message.guild.members, name=member_name, discriminator=member_discriminator)
        if member is None:
            return "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
        else:
            return member.avatar

    def makeEmbed(self, item):        
        if item['hasTime'] == "True":
            mintTime = f"{item['timeType']} {item['mintTime12']} (UTC+9/KST)"
        else:
            mintTime = "NoneTime"
            
        if str(self.mobile) == "online":
            embed=discord.Embed(title=item['name'], description=f"""{mintTime} |  [Twitter]({item['twitterUrl']})  |  [Discord]({item['discordUrl']})\n> **Supply**             {item['supply']} \n> **WL Price**         {item['wlPrice']} {item['blockchain']} \n> **Public Price**   {item['pubPrice']} {item['blockchain']}\n:star: {item['starCount']}     :thumbsup: {item['goodCount']}     :thumbsdown: {item['badCount']}""", color=0x04ff00)
            embed.set_thumbnail(url=item['twitterProfileImage'])
            embed.set_author(name=f"{item['regUser']}", icon_url=f"{item['avatar_url']}")
            embed.set_footer(text=f"by {item['regUser']}")
        else:
            embed=discord.Embed(title=item['name'], description=f"{mintTime} | [Twitter]({item['twitterUrl']}) | [Discord]({item['discordUrl']})", color=0x04ff00)
            embed.set_thumbnail(url=item['twitterProfileImage'])
            embed.set_author(name=f"{item['regUser']}", icon_url=f"{item['avatar_url']}")
            embed.add_field(name=f"""Supply       """, value=f"{item['supply']}", inline=True)
            embed.add_field(name=f"""WL Price     """, value=f"{item['wlPrice']} {item['blockchain']}", inline=True)
            embed.add_field(name=f"""Public Price """, value=f"{item['pubPrice']} {item['blockchain']}", inline=True)
            embed.add_field(name="Star", value=f":star: {item['starCount']}", inline=True)
            embed.add_field(name="Up", value=f":thumbsup: {item['goodCount']}", inline=True)
            embed.add_field(name="Down", value=f":thumbsdown: {item['badCount']}", inline=True)
            embed.set_footer(text=f"by {item['regUser']}")
        return embed

    def regButton(self):
        button_url = f'https://discord.com/api/oauth2/authorize?client_id={discord_client_id}&redirect_uri={quote("https://code.yjsdev.tk/discord-callback/register")}&response_type=code&scope=identify'
        button = discord.ui.Button(style=discord.ButtonStyle.link, label="Go to Registration", url=button_url)
        view = discord.ui.View()
        view.add_item(button)
        return view

    @discord.ui.button(label="AM", row=0, style=discord.ButtonStyle.success)
    async def am_button_callback(self, button, interaction):        
        await interaction.response.defer()
        await self.ctx.send(f"```* {self.day} AM *\n\nSearching...```")

        projects = Queries.select_search_projects(self.db, self.day, "AM")
        index = 1
        for item in projects:
            try:
                avatar_url = await self.get_member_avatar(item['regUser'].split('#')[0], item['regUser'].split('#')[1])
            except Exception as e:
                avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
            item["avatar_url"] = avatar_url
            embed = self.makeEmbed(item)
            embed_message = await self.ctx.send(embed=embed)
            view = UpDownView(self.ctx, embed_message, embed, self.db, item['id'])
            if self.username == item['regUser']:
                button_url = f'https://discord.com/api/oauth2/authorize?client_id={discord_client_id}&redirect_uri={quote("https://code.yjsdev.tk/discord-callback/modify")}&response_type=code&scope=identify'
                button = discord.ui.Button(style=discord.ButtonStyle.link, label="Go to Modify", url=button_url)
                view.add_item(button)
            await embed_message.edit(view=view)
        embed=discord.Embed(title=f"{self.day} AM Mint", description=f"Total {str(len(projects))}", color=0x001eff)
        embed.set_footer(text="Developed from 으노아부지#2642")
        await self.ctx.send(embed=embed)
        await self.ctx.send(view=self.regButton())
        try:
            await interaction.response.send_message("")
        except:
            pass

    @discord.ui.button(label="PM", row=0, style=discord.ButtonStyle.primary)
    async def pm_button_callback(self, button, interaction):
        await interaction.response.defer()
        await self.ctx.send(f"```* {self.day} PM *\n\nSearching...```")

        projects = Queries.select_search_projects(self.db, self.day, "PM")
        for item in projects:
            try:
                avatar_url = await self.get_member_avatar(item['regUser'].split('#')[0], item['regUser'].split('#')[1])
            except Exception as e:
                avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
            item["avatar_url"] = avatar_url
            embed = self.makeEmbed(item)
            embed_message = await self.ctx.send(embed=embed)
            view = UpDownView(self.ctx, embed_message, embed, self.db, item['id'])
            if self.username == item["regUser"]:
                button_url = f'https://discord.com/api/oauth2/authorize?client_id={discord_client_id}&redirect_uri={quote("https://code.yjsdev.tk/discord-callback/modify")}&response_type=code&scope=identify'
                button = discord.ui.Button(style=discord.ButtonStyle.link, label="Go to Modify", url=button_url)
                view.add_item(button)
            await embed_message.edit(view=view)
        embed=discord.Embed(title=f"{self.day} PM Mint", description=f"Total {str(len(projects))}", color=0x001eff)
        embed.set_footer(text="Developed from 으노아부지#2642")
        await self.ctx.send(embed=embed)
        await self.ctx.send(view=self.regButton())
        try:
            await interaction.response.send_message("")
        except:
            pass        

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

class Queries:
    def select_search_projects(db, day, week):
        select_query = f"""
        SELECT  
            A.*,  
            case when mintTime24 > 12 then 'PM' else 'AM' end timeType, 
            SUBSTR( _UTF8'일월화수목금토', DAYOFWEEK(mintDay), 1) AS week 
        FROM ( 
             SELECT
                id, 
                name, 
                ifnull(discordUrl, '-') discordUrl,  
                ifnull(twitterUrl, '-') twitterUrl,  
                ifnull(twitterProfileImage, '-') twitterProfileImage,  
                ifnull(nullif(supply, ''), '-') supply,  
                ifnull(nullif(wlPrice, ''), '-') wlPrice,  
                ifnull(nullif(pubPrice, ''), '-') pubPrice,  
                ifnull(blockchain, '-') blockchain,  
                ifnull(starCount, '0') starCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'UP') goodCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'DOWN') badCount, 
                FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') mintDay, 
                FROM_UNIXTIME(mintDate/1000, '%Y년 %m월 %d일') mintDayKor, 
                FROM_UNIXTIME(mintDate/1000, '%H:%i') mintTime24,  
                FROM_UNIXTIME(mintDate/1000, '%h:%i') mintTime12,
                regUser,
                hasTime  
             FROM projects AA
             WHERE 1=1 
             AND FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') = '{day}' 
             /*AND hasTime = 'True' */
             ORDER BY mintDate ASC 
        ) A 
        WHERE 1=1 
        AND case when mintTime24 > 12 then 'PM' else 'AM' end = '{week}'
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchall()
                return result
    
    def select_all_projects(db, today, tomorrow):
        select_query = f"""
        SELECT  
            A.*,  
            case when mintTime24 > 12 then 'PM' else 'AM' end timeType, 
            SUBSTR( _UTF8'일월화수목금토', DAYOFWEEK(mintDay), 1) AS week
        FROM ( 
             SELECT
                id, 
                name, 
                ifnull(discordUrl, '-') discordUrl, 
                ifnull(twitterUrl, '-') twitterUrl,  
                ifnull(twitterProfileImage, '-') twitterProfileImage,  
                ifnull(nullif(supply, ''), '-') supply,  
                ifnull(nullif(wlPrice, ''), '-') wlPrice,  
                ifnull(nullif(pubPrice, ''), '-') pubPrice,  
                ifnull(blockchain, '-') blockchain,  
                ifnull(starCount, '0') starCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'UP') goodCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'DOWN') badCount,  
                FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') mintDay, 
                FROM_UNIXTIME(mintDate/1000, '%Y년 %m월 %d일') mintDayKor, 
                FROM_UNIXTIME(mintDate/1000, '%H:%i') mintTime24,  
                FROM_UNIXTIME(mintDate/1000, '%h:%i') mintTime12,
                regUser,
                hasTime  
             FROM projects AA
             WHERE 1=1 
             AND FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') >= '{today}' 
             AND FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') <= '{tomorrow}' 
             /*AND hasTime = 'True' */
             /*AND AA.mintDate >= concat(UNIX_TIMESTAMP(now()), '000')*/
             ORDER BY mintDate ASC 
        ) A 
        WHERE 1=1 
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchall()
                return result
            
    def select_today_projects(db, today, tomorrow):
        select_query = f"""
        SELECT  
            A.*,  
            case when mintTime24 > 12 then 'PM' else 'AM' end timeType, 
            SUBSTR( _UTF8'일월화수목금토', DAYOFWEEK(mintDay), 1) AS week
        FROM ( 
             SELECT
                id, 
                name, 
                ifnull(discordUrl, '-') discordUrl, 
                ifnull(twitterUrl, '-') twitterUrl,  
                ifnull(twitterProfileImage, '-') twitterProfileImage,  
                ifnull(nullif(supply, ''), '-') supply,  
                ifnull(nullif(wlPrice, ''), '-') wlPrice,  
                ifnull(nullif(pubPrice, ''), '-') pubPrice,  
                ifnull(blockchain, '-') blockchain,  
                ifnull(starCount, '0') starCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'UP') goodCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'DOWN') badCount,  
                FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') mintDay, 
                FROM_UNIXTIME(mintDate/1000, '%Y년 %m월 %d일') mintDayKor, 
                FROM_UNIXTIME(mintDate/1000, '%H:%i') mintTime24,  
                FROM_UNIXTIME(mintDate/1000, '%h:%i') mintTime12,
                regUser,
                hasTime  
             FROM projects AA
             WHERE 1=1 
             AND FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d %H:%i') >= '{today}' 
             AND FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') <= '{tomorrow}' 
             /*AND hasTime = 'True' */
             AND AA.mintDate >= concat(UNIX_TIMESTAMP(now()), '000')
             ORDER BY mintDate ASC 
        ) A 
        WHERE 1=1 
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchall()
                return result

    def select_one_project(db, project_id):
        select_query = f"""
        SELECT  
            A.*,  
            case when mintTime24 > 12 then 'PM' else 'AM' end timeType, 
            SUBSTR( _UTF8'일월화수목금토', DAYOFWEEK(mintDay), 1) AS week
        FROM ( 
             SELECT
                id, 
                name, 
                ifnull(discordUrl, '-') discordUrl, 
                ifnull(twitterUrl, '-') twitterUrl,  
                ifnull(twitterProfileImage, '-') twitterProfileImage,  
                ifnull(nullif(supply, ''), '-') supply,  
                ifnull(nullif(wlPrice, ''), '-') wlPrice,  
                ifnull(nullif(pubPrice, ''), '-') pubPrice,  
                ifnull(blockchain, '-') blockchain,  
                ifnull(starCount, '0') starCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'UP') goodCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'DOWN') badCount, 
                FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') mintDay, 
                FROM_UNIXTIME(mintDate/1000, '%Y년 %m월 %d일') mintDayKor, 
                FROM_UNIXTIME(mintDate/1000, '%H:%i') mintTime24,  
                FROM_UNIXTIME(mintDate/1000, '%h:%i') mintTime12,
                regUser,
                hasTime  
             FROM projects AA
             WHERE 1=1 
             AND id = '{project_id}'
        ) A 
        WHERE 1=1 
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchone()
                return result

    def select_search_project(db, project_name):
        select_query = f"""
        SELECT  
            A.*,  
            case when mintTime24 > 12 then 'PM' else 'AM' end timeType, 
            SUBSTR( _UTF8'일월화수목금토', DAYOFWEEK(mintDay), 1) AS week
        FROM ( 
             SELECT
                id, 
                name, 
                ifnull(discordUrl, '-') discordUrl, 
                ifnull(twitterUrl, '-') twitterUrl,  
                ifnull(twitterProfileImage, '-') twitterProfileImage,  
                ifnull(nullif(supply, ''), '-') supply,  
                ifnull(nullif(wlPrice, ''), '-') wlPrice,  
                ifnull(nullif(pubPrice, ''), '-') pubPrice,  
                ifnull(blockchain, '-') blockchain,  
                ifnull(starCount, '0') starCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'UP') goodCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'DOWN') badCount, 
                FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') mintDay, 
                FROM_UNIXTIME(mintDate/1000, '%Y년 %m월 %d일') mintDayKor, 
                FROM_UNIXTIME(mintDate/1000, '%H:%i') mintTime24,  
                FROM_UNIXTIME(mintDate/1000, '%h:%i') mintTime12,
                regUser,
                hasTime  
             FROM projects AA
             WHERE 1=1 
             AND upper(replace(name,' ', '')) like upper(replace('%{project_name}%', ' ', ''))
        ) A 
        WHERE 1=1 
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchall()
                return result

    def select_change_date(db, date):
        select_query = f"""
        select 
           a.date_string, 
           STR_TO_DATE(a.date_string, '%Y-%m-%d') date_date 
        from ( 
          select DATE_FORMAT('{date}','%Y-%m-%d') as date_string 
        ) a 
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchone()
                return result

    def merge_recommend(db, project_id, regUser, recommend_type):
        insert_query = f"""
            insert into recommends
            (
                projectId, regUser, recommendType
            ) 
            values 
            (
                '{project_id}', '{regUser}', '{recommend_type}'
            )
            ON DUPLICATE KEY UPDATE recommendType='{recommend_type}';
        """
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(insert_query)
                    conn.commit()
            return {"status":"OK"}
        except Exception as e:
            conn.rollback()
            print(e)
            return {"status": "ERROR", "msg": e}

    def select_my_up(db, regUser, today, tomorrow):
        select_query = f"""
        SELECT  
            A.*,  
            case when mintTime24 > 12 then 'PM' else 'AM' end timeType, 
            SUBSTR( _UTF8'일월화수목금토', DAYOFWEEK(mintDay), 1) AS week 
        FROM ( 
             SELECT
                AA.id, 
                name, 
                ifnull(discordUrl, '-') discordUrl,  
                ifnull(twitterUrl, '-') twitterUrl,  
                ifnull(twitterProfileImage, '-') twitterProfileImage,  
                ifnull(nullif(supply, ''), '-') supply,  
                ifnull(nullif(wlPrice, ''), '-') wlPrice,  
                ifnull(nullif(pubPrice, ''), '-') pubPrice,  
                ifnull(blockchain, '-') blockchain,  
                ifnull(starCount, '0') starCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'UP') goodCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'DOWN') badCount, 
                FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') mintDay, 
                FROM_UNIXTIME(mintDate/1000, '%Y년 %m월 %d일') mintDayKor, 
                FROM_UNIXTIME(mintDate/1000, '%H:%i') mintTime24,  
                FROM_UNIXTIME(mintDate/1000, '%h:%i') mintTime12,
                AA.regUser  
             FROM projects AA
             INNER JOIN recommends BB ON BB.projectId = AA.id
             WHERE 1=1 
             AND BB.regUser = '{regUser}'
             AND BB.recommendType = 'UP'
             /*AND AA.mintDate >= concat(UNIX_TIMESTAMP(now()), '000')*/
             AND FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') >= '{today}' 
             AND FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') <= '{tomorrow}'
             ORDER BY mintDate ASC 
        ) A 
        WHERE 1=1 
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchall()
                return result

    def select_ranking(db, month):
        select_query = f"""
        SELECT
            DENSE_RANK() OVER (ORDER BY up_score DESC) AS ranking,
            id,
            name,
            twitterUrl,
            discordUrl,
            FROM_UNIXTIME(mintDate/1000, '%%Y-%%m-%%d %%H:%%i') mintDate,
            up_score,
            down_score,
            star_score
        FROM (
                 SELECT
                     c.id,
                     c.name,
                     c.mintDate,
                     c.twitterUrl,
                     c.discordUrl,
                     SUM(c.up_score) AS up_score,
                     SUM(c.down_score) AS down_score,
                     MAX(c.star_score) AS star_score
                 FROM (
                          SELECT
                              a.id,
                              a.name,
                              a.mintDate,
                              a.twitterUrl,
                              a.discordUrl,
                              CASE WHEN b.recommendType = 'UP' THEN 1
                                   ELSE 0
                                  END up_score,
                              CASE WHEN b.recommendType = 'DOWN' THEN 1
                                   ELSE 0
                                  END down_score,
                              CASE WHEN COALESCE(a.starCount, 0) = '' THEN 0
                                  ELSE COALESCE(a.starCount, 0)
                                END star_score
                          FROM projects a
                                   LEFT OUTER JOIN recommends b ON a.id = b.projectId
                           /*WHERE FROM_UNIXTIME(a.mintDate/1000, '%%Y%%m') = COALESCE(%s, DATE_FORMAT(NOW(), '%%Y%%m'))*/
                            WHERE a.mintDate >= concat(UNIX_TIMESTAMP(now()), '000')
                      ) c
                 GROUP BY c.id, c.name, c.twitterUrl, c.discordUrl
             ) d
        ORDER BY up_score DESC
        LIMIT 10;
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, (month,))
                result = cursor.fetchall()
                return result

    def add_recommendation(db, project_id, reg_user, recommend_type):
        insert_query = f"""
        INSERT INTO recommends (projectId, regUser, recommendType)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE recommendType=%s;
        """

        previous_recommendation = Queries.get_previous_recommendation(db, project_id, reg_user)
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(insert_query, (project_id, reg_user, recommend_type, recommend_type))
                conn.commit()

        return previous_recommendation

    def get_previous_recommendation(db, project_id, reg_user):
        select_query = f"""
        SELECT recommendType FROM recommends WHERE projectId=%s AND regUser=%s;
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, (project_id, reg_user))
                result = cursor.fetchone()

        if result:
            return result['recommendType']
        return None


    def get_project_id_by_twitter_handle(db, twitter_handle):
        select_query = f"""
        SELECT id
        FROM projects
        WHERE twitterUrl LIKE replace(%s, '@', '');
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, (f"%{twitter_handle}",))
                result = cursor.fetchone()

        if result is None:
            return None

        return result

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())
paginator = Paginator(bot)
paginator_search = Paginator(bot)
db = Database(mysql_ip, mysql_port, mysql_id, mysql_passwd, mysql_db)
days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

@bot.event
async def on_ready():
    print("다음으로 로그인합니다: ")
    print(bot.user.name)
    print("connection was succesful")
    await bot.change_presence(status=discord.Status.online, activity=None)

@bot.command()
async def m(ctx):
    bot_channel_id = 1089590412164993044
    if ctx.channel.id != 1088659865397903391:
        if ctx.channel.id != bot_channel_id:
            await ctx.reply(f"This command only works in <#{bot_channel_id}> channel.", mention_author=True)
        return

    today = datetime.datetime.now().date()
    date_string = today.strftime("%Y-%m-%d")
    day = today.weekday()
    
    embed=discord.Embed(title=f"**{date_string} {days[day]}**")
    await ctx.send(embed=embed)
    await ctx.send("", view=ButtonView(ctx, db, date_string))

    tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).date()
    date_string = tomorrow.strftime("%Y-%m-%d")
    day = tomorrow.weekday()

    embed=discord.Embed(title=f"**{date_string} {days[day]}**")
    await ctx.send(embed=embed)
    await ctx.send("", view=ButtonView(ctx, db, date_string))

    button_url = f'https://discord.com/api/oauth2/authorize?client_id={discord_client_id}&redirect_uri={quote("https://code.yjsdev.tk/discord-callback/register")}&response_type=code&scope=identify'
    button = discord.ui.Button(style=discord.ButtonStyle.link, label="Go to Registration", url=button_url)
    view = discord.ui.View()
    view.add_item(button)
    await ctx.send(view=view)

@bot.command()
async def mday(ctx, date):
    bot_channel_id = 1089590412164993044
    if ctx.channel.id != bot_channel_id:
        await ctx.reply(f"This command only works in <#{bot_channel_id}> channel.", mention_author=True)
        return

    try:
        date_db = Queries.select_change_date(db, date)
        day = date_db['date_date'].weekday()
    except Exception as e:
        print("Error:", e)
        await ctx.send("```Please enter 'yyyymmdd' or 'yyyy-mm-dd' date format.```")
        return

    embed=discord.Embed(title=f"**{date_db['date_string']} {days[day]}**")
    await ctx.send(embed=embed)
    await ctx.send("", view=ButtonView(ctx, db, date_db['date_string']))

@bot.command()
async def mpage(ctx):
    today = datetime.datetime.now().date()
    today_string = today.strftime("%Y-%m-%d")
    tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).date()
    tomorrow_string = tomorrow.strftime("%Y-%m-%d")

    buttonView = ButtonView(ctx, db, "")
    pages = []
    projects = Queries.select_all_projects(db, today_string, tomorrow_string)
    before_mint_day = ""
    color = "-"
    for item in projects:
        try:
            avatar_url = await buttonView.get_member_avatar(item['regUser'].split('#')[0], item['regUser'].split('#')[1])
        except Exception as e:
            avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
        item["avatar_url"] = avatar_url
        embed=buttonView.makeEmbed(item)

        if before_mint_day == "":
            before_mint_day = item['mintDay']
        if before_mint_day != item['mintDay']:
            color = "+" 
        cal = Page(content=f"```diff\n{color}[{item['mintDay']}]{color}```", embed=embed)
        pages.append(cal)

    await paginator.send(ctx.channel, pages, type=NavigationType.Buttons)

@bot.command()
async def mint(ctx, *, arg="today"):
    if arg == "today":
        today = datetime.datetime.now().date()
        tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).date()
    else:
        try:
            target_date = datetime.datetime.strptime(arg, "%Y%m%d").date()
        except ValueError:
            await ctx.reply("잘못된 날짜 형식입니다. 다시 시도해주세요. (yyyymmdd)", mention_author=True)
            return
        today = target_date
        tomorrow = target_date + datetime.timedelta(days=1)
    today_string = today.strftime("%Y-%m-%d")
    tomorrow_string = tomorrow.strftime("%Y-%m-%d")

    buttonView = ButtonView(ctx, db, "")
    pages = []
    if arg == "today":
        projects = Queries.select_today_projects(db, today_string, tomorrow_string)
    else:
        projects = Queries.select_all_projects(db, today_string, tomorrow_string)
    before_mint_day = ""
    color = "-"
    for item in projects:
        try:
            avatar_url = await buttonView.get_member_avatar(item['regUser'].split('#')[0], item['regUser'].split('#')[1])
        except Exception as e:
            avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
        item["avatar_url"] = avatar_url
        embed=buttonView.makeEmbed(item)

        if before_mint_day == "":
            before_mint_day = item['mintDay']
        if before_mint_day != item['mintDay']:
            color = "+" 
        cal = Page(content=f"```diff\n{color}[{item['mintDay']}]{color}```", embed=embed)
        pages.append(cal)

    await paginator.send(ctx.channel, pages, type=NavigationType.Buttons)

@bot.command()
async def my(ctx):
    try:
        regUser = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"
        today = datetime.datetime.now().date()
        today_string = today.strftime("%Y-%m-%d")
        tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).date()
        tomorrow_string = tomorrow.strftime("%Y-%m-%d")

        embed=discord.Embed(title=f"**Today {regUser} Mint List**", description="")

        my_up_list = Queries.select_my_up(db, regUser, today_string, tomorrow_string)
        before_date = ""
        before_time = ""
        list_massage = "\n"
        if len(my_up_list) > 0:
            for item in my_up_list:
                if len(list_massage) > 900:
                    embed.add_field(name="", value=list_massage, inline=True)
                    await ctx.send(embed=embed)
                    embed=discord.Embed(title="", description="")
                    list_massage = "\n"         
                item_date = f"{item['mintDay']}"
                item_time = f"{item['mintTime24']}"
                if before_date != item_date:
                    list_massage = list_massage + f"""\n\n**{item_date}**\n"""
                    before_date = item_date
                    before_time = ""
                if before_time != item_time:
                    if before_time != "": 
                        list_massage = list_massage + "\n"
                    list_massage = list_massage + f"""{item_time}\n"""
                    before_time = item_time
                list_massage = list_massage + f"""> [{item['name']}]({item['twitterUrl']})  /  Supply: {item['supply']}  / WL: {item['wlPrice']} {item['blockchain']}  /  Public: {item['pubPrice']} {item['blockchain']}\n"""
                # print(len(list_massage))
            list_massage = list_massage + ""
        else:
            update_channel = await bot.fetch_channel(1089590412164993044)
            mention_string = update_channel.mention
            list_massage = list_massage + f"No projects have been recommend.\n\nPlease go to {mention_string} Channel and press UP for the project you want to recommend."
    except Exception as e:
        print("Error:", e)
        return

    
    embed.add_field(name="", value=list_massage, inline=True)
    await ctx.send(embed=embed)


@bot.command()
async def your(ctx, dc_id):
    try:
        print(dc_id[2:-1])
        user = await bot.fetch_user(dc_id[2:-1])
        print(user)
        if user is not None:
            print(f"이름: {user.name}")
            print(f"디스크리미네이터: {user.discriminator}")
            regUser = user.name + "#" + user.discriminator
        else:
            regUser = dc_id


        embed=discord.Embed(title=f"**Today {regUser} Mint List**", description="")

        my_up_list = Queries.select_my_up(db, regUser)
        before_date = ""
        before_time = ""
        list_massage = "\n"
        if len(my_up_list) > 0:
            for item in my_up_list:
                if len(list_massage) > 900:
                    embed.add_field(name="", value=list_massage, inline=True)
                    await ctx.send(embed=embed)
                    embed=discord.Embed(title="", description="")
                    list_massage = "\n"         
                item_date = f"{item['mintDay']}"
                item_time = f"{item['mintTime24']}"
                if before_date != item_date:
                    list_massage = list_massage + f"""\n\n**{item_date}**\n"""
                    before_date = item_date
                    before_time = ""
                if before_time != item_time:
                    if before_time != "": 
                        list_massage = list_massage + "\n"
                    list_massage = list_massage + f"""{item_time}\n"""
                    before_time = item_time
                list_massage = list_massage + f"""> [{item['name']}]({item['twitterUrl']})  /  Supply: {item['supply']}  / WL: {item['wlPrice']} {item['blockchain']}  /  Public: {item['pubPrice']} {item['blockchain']}\n"""
                # print(len(list_massage))
            list_massage = list_massage + ""
        else:
            list_massage = list_massage + f"No projects have been recommend."
    except Exception as e:
        print("Error:", e)
        return

    
    embed.add_field(name="", value=list_massage, inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def msearch(ctx, project_name):
    buttonView = ButtonView(ctx, db, "")
    pages = []
    projects = Queries.select_search_project(db, project_name)
    before_mint_day = ""
    color = "-"
    if len(projects) > 0:
        for item in projects:
            try:
                avatar_url = await buttonView.get_member_avatar(item['regUser'].split('#')[0], item['regUser'].split('#')[1])
            except Exception as e:
                avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
            item["avatar_url"] = avatar_url
            embed=buttonView.makeEmbed(item)

            if before_mint_day == "":
                before_mint_day = item['mintDay']
            if before_mint_day != item['mintDay']:
                if color == "+":
                    color = "-" 
                else:
                    color = "+"
            cal = Page(content=f"```diff\n{color}[{item['mintDay']}]{color}```", embed=embed)
            pages.append(cal)

        await paginator_search.send(ctx.channel, pages, type=NavigationType.Buttons)
    else:
        await ctx.reply(f"```No projects have been searched as '{project_name}'.\n\nPlease search for another word.```", mention_author=True)

@bot.command()
async def mrank(ctx):
    results = Queries.select_ranking(db, None)

    pages = []

    for page in range(5):
        embed = Embed(title=f"Top {page * 10 + 1} ~ {page * 10 + 10} Rank\n", color=0x00ff00)

        for i in range(10):
            index = page * 10 + i
            if index >= len(results):
                break

            item = results[index]
            link_url = f"[Twitter]({item['twitterUrl']})"
            if item['discordUrl']:
                link_url = f"{link_url}  |  [Discord]({item['discordUrl']})"

            field_name = f"`{item['ranking']}.` {item['name']} :thumbsup: {item['up_score']}  :thumbsdown: {item['down_score']}"
            field_value = f"{item['mintDate']} (KST)  |  {link_url}"
            embed.add_field(name=field_name, value=field_value, inline=False)
            embed.set_footer(text=f"by SearchFI Bot")

        cal = Page(content=f"**🏆 Project Ranking Top 50 🏆**", embed=embed)
        pages.append(cal)

    paginator = Paginator(bot)
    await paginator.send(ctx.channel, pages, type=NavigationType.Buttons)

    button_url = f'https://discord.com/api/oauth2/authorize?client_id={discord_client_id}&redirect_uri={quote("https://code.yjsdev.tk/discord-callback/register")}&response_type=code&scope=identify'
    button = discord.ui.Button(style=discord.ButtonStyle.green, label="Go to Registration", url=button_url)
    view = discord.ui.View()
    view.add_item(button)
    await ctx.send(view=view)

@bot.command()
async def mup(ctx, twitter_handle: str):
    user_id = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"

    # Find the project ID by Twitter handle
    project_info = Queries.get_project_id_by_twitter_handle(db, twitter_handle)

    if project_info is None:
        await ctx.reply(f"❌ Could not find a project for `{twitter_handle}`.", mention_author=True)
        return

    project_id = project_info['id']

    # Add recommendation to the database and get the previous recommendation type
    previous_recommendation = Queries.add_recommendation(db, project_id, user_id, "UP")

    # Send an appropriate message
    if previous_recommendation is None:
        await ctx.reply(f"✅ Successfully recommended `{twitter_handle}` project!", mention_author=True)
    elif previous_recommendation == "UP":
        await ctx.reply(f"ℹ️ You have already recommended `{twitter_handle}` project.", mention_author=True)
    else:  # previous_recommendation == "DOWN"
        await ctx.reply(f":thumbup: Changed your downvote to an upvote for `{twitter_handle}` project!", mention_author=True)

@bot.command()
async def mdown(ctx, twitter_handle: str):
    user_id = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"

    # Find the project ID by Twitter handle
    project_info = Queries.get_project_id_by_twitter_handle(db, twitter_handle)

    if project_info is None:
        await ctx.reply(f"❌ Could not find a project for `{twitter_handle}`.", mention_author=True)
        return

    project_id = project_info['id']

    # Add downvote to the database and get the previous recommendation type
    previous_recommendation = Queries.add_recommendation(db, project_id, user_id, "DOWN")

    # Send an appropriate message
    if previous_recommendation is None:
        await ctx.reply(f"❌ Successfully downvoted `{twitter_handle}` project!", mention_author=True)
    elif previous_recommendation == "DOWN":
        await ctx.reply(f"ℹ️ You have already downvoted `{twitter_handle}` project.", mention_author=True)
    else:  # previous_recommendation == "UP"
        await ctx.reply(f":thumbdown: Changed your upvote to a downvote for `{twitter_handle}` project!", mention_author=True)

def get_current_price(token):
    url = f"https://api.bithumb.com/public/ticker/{token}_KRW"
    headers = {"accept": "application/json"}
    response = requests.get(url, headers=headers)
    data = response.json()

    if data["status"] == "0000":
        return float(data["data"]["closing_price"])
    else:
        return None

@bot.command()
async def lm(ctx, amount: float = 1):
    current_price = get_current_price('LM')
    if current_price is not None:
        current_price_rounded = round(current_price, 1)
        total_price = current_price * amount
        total_price_rounded = round(total_price, 1)

        embed = Embed(title="LM Price", color=0x3498db)
        embed.add_field(name="1 LM", value=f"```\n{format(int(str(current_price_rounded).split('.')[0]), ',')}.{str(current_price_rounded).split('.')[1]} KRW\n```", inline=True)
        embed.add_field(name=f"{amount} LM", value=f"```\n{format(int(str(total_price_rounded).split('.')[0]), ',')}.{str(total_price_rounded).split('.')[1]} KRW\n```", inline=True)
        embed.set_footer(text="Data from Bithumb", icon_url="https://content.bithumb.com/resources/img/comm/seo/favicon-96x96.png?v=bithumb.2.0.4")

        await ctx.reply(embed=embed, mention_author=True)
    else:
        await ctx.reply("Error: Could not fetch the price.", mention_author=True)

@bot.command()
async def sui(ctx, amount: float = 1):
    current_price = get_current_price('SUI')
    if current_price is not None:
        current_price_rounded = round(current_price, 1)
        total_price = current_price * amount
        total_price_rounded = round(total_price, 1)

        embed = Embed(title="SUI Price", color=0x3498db)
        embed.add_field(name="1 SUI", value=f"```\n{format(int(str(current_price_rounded).split('.')[0]), ',')}.{str(current_price_rounded).split('.')[1]} KRW\n```", inline=True)
        embed.add_field(name=f"{amount} SUI", value=f"```\n{format(int(str(total_price_rounded).split('.')[0]), ',')}.{str(total_price_rounded).split('.')[1]} KRW\n```", inline=True)
        embed.set_footer(text="Data from Bithumb", icon_url="https://content.bithumb.com/resources/img/comm/seo/favicon-96x96.png?v=bithumb.2.0.4")

        await ctx.reply(embed=embed, mention_author=True)
    else:
        await ctx.reply("Error: Could not fetch the price.", mention_author=True)

@bot.command()
async def bnb(ctx, amount: float = 1):
    current_price = get_current_price('BNB')
    if current_price is not None:
        current_price_rounded = round(current_price, 1)
        total_price = current_price * amount
        total_price_rounded = round(total_price, 1)

        embed = Embed(title="BNB Price", color=0x3498db)
        embed.add_field(name="1 BNB", value=f"```\n{format(int(str(current_price_rounded).split('.')[0]), ',')}.{str(current_price_rounded).split('.')[1]} KRW\n```", inline=True)
        embed.add_field(name=f"{amount} BNB", value=f"```\n{format(int(str(total_price_rounded).split('.')[0]), ',')}.{str(total_price_rounded).split('.')[1]} KRW\n```", inline=True)
        embed.set_footer(text="Data from Bithumb", icon_url="https://content.bithumb.com/resources/img/comm/seo/favicon-96x96.png?v=bithumb.2.0.4")

        await ctx.reply(embed=embed, mention_author=True)
    else:
        await ctx.reply("Error: Could not fetch the price.", mention_author=True)

bot.run(bot_token)

