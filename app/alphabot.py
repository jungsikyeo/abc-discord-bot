import datetime
import time
import pymysql
import discord
import requests
import os
import cloudscraper
import cfscrape
import json
import pytz
from pytz import all_timezones, timezone
from discord.ui import Button, View
from discord.ext import commands
from discord import Embed
from paginator import Paginator, Page, NavigationType
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB
from urllib.parse import quote, urlparse
from dotenv import load_dotenv

load_dotenv()

command_flag = os.getenv("SEARCHFI_BOT_FLAG")
bot_token = os.getenv("SEARCHFI_BOT_TOKEN")
mysql_ip = os.getenv("MYSQL_IP")
mysql_port = os.getenv("MYSQL_PORT")
mysql_id = os.getenv("MYSQL_ID")
mysql_passwd = os.getenv("MYSQL_PASSWD")
mysql_db = os.getenv("MYSQL_DB")
bot_domain=os.getenv("SEARCHFI_BOT_DOMAIN")
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
            mintTime = f"<t:{int(item['unixMintDate'])}>"
        else:
            mintTime = "NoneTime"

        link_url = f"[Twitter]({item['twitterUrl']})"
        if item['discordUrl'] and item['discordUrl'] != '-':
            link_url = f"{link_url}  |  [Discord]({item['discordUrl']})"
        if item['walletCheckerUrl'] != '-':
            link_url = f"{link_url}  |  [Checker]({item['walletCheckerUrl']})"

        if str(self.mobile) == "online":
            embed=discord.Embed(title=item['name'], description=f"""{mintTime} | {link_url}\n> **Supply**             {item['supply']} \n> **WL Price**         {item['wlPrice']} {item['blockchain']} \n> **Public Price**   {item['pubPrice']} {item['blockchain']}\n:thumbsup: {item['goodCount']}     :thumbsdown: {item['badCount']}""", color=0x04ff00)
            embed.set_thumbnail(url=item['twitterProfileImage'])
            embed.set_author(name=f"{item['regUser']}", icon_url=f"{item['avatar_url']}")
            embed.set_footer(text="Powered by 으노아부지#2642")
        else:
            embed=discord.Embed(title=item['name'], description=f"{mintTime} | {link_url}", color=0x04ff00)
            embed.set_thumbnail(url=item['twitterProfileImage'])
            embed.set_author(name=f"{item['regUser']}", icon_url=f"{item['avatar_url']}")
            embed.add_field(name=f"""Supply       """, value=f"{item['supply']}", inline=True)
            embed.add_field(name=f"""WL Price     """, value=f"{item['wlPrice']} {item['blockchain']}", inline=True)
            embed.add_field(name=f"""Public Price """, value=f"{item['pubPrice']} {item['blockchain']}", inline=True)
            embed.add_field(name="Up", value=f":thumbsup: {item['goodCount']}", inline=True)
            embed.add_field(name="Down", value=f":thumbsdown: {item['badCount']}", inline=True)
            embed.set_footer(text="Powered by 으노아부지#2642")
        return embed

    def regButton(self):
        button_url = f'https://discord.com/api/oauth2/authorize?client_id={discord_client_id}&redirect_uri={quote(f"{bot_domain}/discord-callback/register")}&response_type=code&scope=identify'
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
                button_url = f'https://discord.com/api/oauth2/authorize?client_id={discord_client_id}&redirect_uri={quote(f"{bot_domain}/discord-callback/modify")}&response_type=code&scope=identify'
                button = discord.ui.Button(style=discord.ButtonStyle.link, label="Go to Modify", url=button_url)
                view.add_item(button)
            await embed_message.edit(view=view)
        embed=discord.Embed(title=f"{self.day} AM Mint", description=f"Total {str(len(projects))}", color=0x001eff)
        embed.set_footer(text="Powered by 으노아부지#2642")
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
                button_url = f'https://discord.com/api/oauth2/authorize?client_id={discord_client_id}&redirect_uri={quote(f"{bot_domain}/discord-callback/modify")}&response_type=code&scope=identify'
                button = discord.ui.Button(style=discord.ButtonStyle.link, label="Go to Modify", url=button_url)
                view.add_item(button)
            await embed_message.edit(view=view)
        embed=discord.Embed(title=f"{self.day} PM Mint", description=f"Total {str(len(projects))}", color=0x001eff)
        embed.set_footer(text="Powered by 으노아부지#2642")
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
            case when mintTime24 > 12 then 'PM' else 'AM' end timeType
        FROM ( 
             SELECT
                id, 
                name, 
                ifnull(discordUrl, '-') discordUrl,  
                ifnull(twitterUrl, '-') twitterUrl,  
                ifnull(walletCheckerUrl, '-') walletCheckerUrl,  
                ifnull(twitterProfileImage, '-') twitterProfileImage,  
                ifnull(nullif(supply, ''), '-') supply,  
                ifnull(nullif(wlPrice, ''), '-') wlPrice,  
                ifnull(nullif(pubPrice, ''), '-') pubPrice,  
                ifnull(blockchain, '-') blockchain,  
                ifnull(starCount, '0') starCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'UP') goodCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'DOWN') badCount, 
                mintDate/1000 unixMintDate,
                case when mintDate = 'TBA' then mintDate else FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') end mintDay,
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
            case when mintTime24 > 12 then 'PM' else 'AM' end timeType
        FROM ( 
             SELECT
                id, 
                name, 
                ifnull(discordUrl, '-') discordUrl, 
                ifnull(twitterUrl, '-') twitterUrl,  
                ifnull(walletCheckerUrl, '-') walletCheckerUrl,  
                ifnull(twitterProfileImage, '-') twitterProfileImage,  
                ifnull(nullif(supply, ''), '-') supply,  
                ifnull(nullif(wlPrice, ''), '-') wlPrice,  
                ifnull(nullif(pubPrice, ''), '-') pubPrice,  
                ifnull(blockchain, '-') blockchain,  
                ifnull(starCount, '0') starCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'UP') goodCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'DOWN') badCount,  
                mintDate/1000 unixMintDate,
                case when mintDate = 'TBA' then mintDate else FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') end mintDay, 
                FROM_UNIXTIME(mintDate/1000, '%H:%i') mintTime24,  
                FROM_UNIXTIME(mintDate/1000, '%h:%i') mintTime12,
                regUser,
                hasTime  
             FROM projects AA
             WHERE 1=1 
             AND FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d %H:%i') >= '{today}' 
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
            case when mintTime24 > 12 then 'PM' else 'AM' end timeType
        FROM ( 
             SELECT
                id, 
                name, 
                ifnull(discordUrl, '-') discordUrl, 
                ifnull(twitterUrl, '-') twitterUrl,  
                ifnull(walletCheckerUrl, '-') walletCheckerUrl,  
                ifnull(twitterProfileImage, '-') twitterProfileImage,  
                ifnull(nullif(supply, ''), '-') supply,  
                ifnull(nullif(wlPrice, ''), '-') wlPrice,  
                ifnull(nullif(pubPrice, ''), '-') pubPrice,  
                ifnull(blockchain, '-') blockchain,  
                ifnull(starCount, '0') starCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'UP') goodCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'DOWN') badCount,
                mintDate/1000 unixMintDate,  
                case when mintDate = 'TBA' then mintDate else FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') end mintDay, 
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
            case when mintTime24 > 12 then 'PM' else 'AM' end timeType
        FROM ( 
             SELECT
                id, 
                name, 
                ifnull(discordUrl, '-') discordUrl, 
                ifnull(twitterUrl, '-') twitterUrl,  
                ifnull(walletCheckerUrl, '-') walletCheckerUrl,  
                ifnull(twitterProfileImage, '-') twitterProfileImage,  
                ifnull(nullif(supply, ''), '-') supply,  
                ifnull(nullif(wlPrice, ''), '-') wlPrice,  
                ifnull(nullif(pubPrice, ''), '-') pubPrice,  
                ifnull(blockchain, '-') blockchain,  
                ifnull(starCount, '0') starCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'UP') goodCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'DOWN') badCount,
                mintDate/1000 unixMintDate, 
                case when mintDate = 'TBA' then mintDate else FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') end mintDay, 
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
            case when mintTime24 > 12 then 'PM' else 'AM' end timeType
        FROM ( 
             SELECT
                id, 
                name, 
                ifnull(discordUrl, '-') discordUrl, 
                ifnull(twitterUrl, '-') twitterUrl,  
                ifnull(walletCheckerUrl, '-') walletCheckerUrl,  
                ifnull(twitterProfileImage, '-') twitterProfileImage,  
                ifnull(nullif(supply, ''), '-') supply,  
                ifnull(nullif(wlPrice, ''), '-') wlPrice,  
                ifnull(nullif(pubPrice, ''), '-') pubPrice,  
                ifnull(blockchain, '-') blockchain,  
                ifnull(starCount, '0') starCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'UP') goodCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'DOWN') badCount, 
                mintDate/1000 unixMintDate,
                case when mintDate = 'TBA' then mintDate else FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') end mintDay, 
                FROM_UNIXTIME(mintDate/1000, '%H:%i') mintTime24,  
                FROM_UNIXTIME(mintDate/1000, '%h:%i') mintTime12,
                regUser,
                hasTime  
             FROM projects AA
             WHERE 1=1 
             AND (
                 upper(replace(name,' ', '')) like upper(replace('%{project_name}%', ' ', '')) 
                 or upper(replace(twitterUrl,'https://twitter.com/', '')) like upper(replace('%{project_name}%', ' ', ''))
             )
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
            case when mintTime24 > 12 then 'PM' else 'AM' end timeType
        FROM ( 
             SELECT
                AA.id, 
                name, 
                ifnull(discordUrl, '-') discordUrl,  
                ifnull(twitterUrl, '-') twitterUrl,  
                ifnull(walletCheckerUrl, '-') walletCheckerUrl,  
                ifnull(twitterProfileImage, '-') twitterProfileImage,  
                ifnull(nullif(supply, ''), '-') supply,  
                ifnull(nullif(wlPrice, ''), '-') wlPrice,  
                ifnull(nullif(pubPrice, ''), '-') pubPrice,  
                ifnull(blockchain, '-') blockchain,  
                ifnull(starCount, '0') starCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'UP') goodCount,  
                (select count(1) from recommends where projectId = AA.id and recommendType = 'DOWN') badCount, 
                mintDate/1000 unixMintDate,
                case when mintDate = 'TBA' then mintDate else FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') end mintDay, 
                FROM_UNIXTIME(mintDate/1000, '%Y년 %m월 %d일') mintDayKor, 
                FROM_UNIXTIME(mintDate/1000, '%H:%i') mintTime24,  
                FROM_UNIXTIME(mintDate/1000, '%h:%i') mintTime12,
                AA.regUser,
                AA.hasTime
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

    def select_ranking(db):
        select_query = f"""
        SELECT
            DENSE_RANK() OVER (ORDER BY (up_score - down_score) DESC) AS ranking,
            id,
            name,
            twitterUrl,
            discordUrl,
            walletCheckerUrl,
            case when mintDate = 'TBA' then mintDate else FROM_UNIXTIME(mintDate/1000, '%%Y-%%m-%%d %%H:%%i') end mintDate,
            mintDate/1000 unixMintDate,
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
                     c.walletCheckerUrl,
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
                              a.walletCheckerUrl,
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
                           WHERE a.mintDate >= concat(UNIX_TIMESTAMP(now()), '000')
                      ) c
                 GROUP BY c.id, c.name, c.twitterUrl, c.discordUrl, c.walletCheckerUrl
                 having (up_score + down_score) > 0
             ) d
        ORDER BY (up_score - down_score) DESC
        LIMIT 50;
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchall()
                return result

    def select_my_ranking(db, regUser):
        select_query = f"""
        SELECT f.*
        FROM (
                 SELECT
                     DENSE_RANK() OVER (ORDER BY (up_score - down_score) DESC) AS ranking,
                     regUser,
                     id,
                     name,
                     twitterUrl,
                     discordUrl,
                     walletCheckerUrl,
                     case when mintDate = 'TBA' then mintDate else FROM_UNIXTIME(mintDate/1000, '%%Y-%%m-%%d %%H:%%i') end mintDate,
                     mintDate/1000 unixMintDate,
                     up_score,
                     down_score,
                     star_score
                 FROM (
                          SELECT
                              c.regUser,
                              c.id,
                              c.name,
                              c.mintDate,
                              c.twitterUrl,
                              c.discordUrl,
                              c.walletCheckerUrl,
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
                                       a.walletCheckerUrl,
                                       CASE WHEN b.recommendType = 'UP' THEN 1
                                            ELSE 0
                                           END up_score,
                                       CASE WHEN b.recommendType = 'DOWN' THEN 1
                                            ELSE 0
                                           END down_score,
                                       CASE WHEN COALESCE(a.starCount, 0) = '' THEN 0
                                            ELSE COALESCE(a.starCount, 0)
                                           END star_score,
                                       a.regUser
                                   FROM projects a
                                            LEFT OUTER JOIN recommends b ON a.id = b.projectId
                                   WHERE a.mintDate >= concat(UNIX_TIMESTAMP(now()), '000')
                               ) c
                          GROUP BY c.id, c.name, c.twitterUrl, c.discordUrl, c.walletCheckerUrl, c.regUser
                          having (up_score + down_score) > 0
                      ) d
                 ORDER BY (up_score - down_score) DESC
                 LIMIT 50
             ) f
        WHERE regUser = %s
        ORDER BY ranking ASC
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, (regUser,))
                result = cursor.fetchall()
                return result

    def select_my_updown(db, regUser, type):
        select_query = f"""
        SELECT f.*
        FROM (
                 SELECT
                     DENSE_RANK() OVER (ORDER BY (up_score - down_score) DESC) AS ranking,
                     regUser,
                     id,
                     name,
                     twitterUrl,
                     discordUrl,
                     walletCheckerUrl,
                     case when mintDate = 'TBA' then mintDate else FROM_UNIXTIME(mintDate/1000, '%%Y-%%m-%%d %%H:%%i') end mintDate,
                     mintDate/1000 unixMintDate,
                     up_score,
                     down_score,
                     star_score
                 FROM (
                          SELECT
                              c.regUser,
                              c.id,
                              c.name,
                              c.mintDate,
                              c.twitterUrl,
                              c.discordUrl,
                              c.walletCheckerUrl,
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
                                       a.walletCheckerUrl,
                                       CASE WHEN b.recommendType = 'UP' THEN 1
                                            ELSE 0
                                           END up_score,
                                       CASE WHEN b.recommendType = 'DOWN' THEN 1
                                            ELSE 0
                                           END down_score,
                                       CASE WHEN COALESCE(a.starCount, 0) = '' THEN 0
                                            ELSE COALESCE(a.starCount, 0)
                                           END star_score,
                                       a.regUser
                                   FROM projects a
                                            LEFT OUTER JOIN recommends b ON a.id = b.projectId
                                   WHERE a.mintDate >= concat(UNIX_TIMESTAMP(now()), '000')
                               ) c
                          GROUP BY c.id, c.name, c.twitterUrl, c.discordUrl, c.walletCheckerUrl, c.regUser
                          having (up_score + down_score) > 0
                      ) d
                 ORDER BY (up_score - down_score) DESC
             ) f
            INNER JOIN recommends r ON f.id = r.projectId
        WHERE r.regUser = %s
        AND r.recommendType = %s
        ORDER BY ranking ASC
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, (regUser, type))
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
        WHERE twitterUrl LIKE replace(replace(%s, '@', ''), ' ', '');
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, (f"%{twitter_handle}",))
                result = cursor.fetchone()

        if result is None:
            return None

        return result

    def update_wallet_checker_url(db, project_id, wallet_checker_url):
        update_query = "UPDATE projects SET walletCheckerUrl = %s WHERE id = %s"

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(update_query, (wallet_checker_url, project_id))
                conn.commit()

    def get_tier_by_blockchain(db, blockchain):
        select_query = f"""
        SELECT imageUrl
        FROM tiers
        WHERE blockchain = case when upper(%s) = null then 'ETH' else upper(%s) end;
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, (blockchain, blockchain,))
                result = cursor.fetchone()

        if result is None:
            return None

        return result

    def update_tier_url(db, blockchain, image_url, reg_user):
        update_query = """
        INSERT INTO tiers (blockchain, imageUrl, regUser)
        VALUES (upper(%s), %s, %s)
        ON DUPLICATE KEY UPDATE imageUrl = %s, regUser = %s
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(update_query, (blockchain, image_url, reg_user, image_url, reg_user,))
                conn.commit()

    def select_keyword(db, keyword):
        select_query = f"""
        SELECT *
        FROM keywords
        WHERE keyword = %s;
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, (keyword,))
                result = cursor.fetchone()

        if result is None:
            return None

        return result

    def update_keyword(db, blockchain, keyword, symbol, reg_user):
        update_query = """
        INSERT INTO keywords (blockchain, keyword, symbol, regUser)
        VALUES (upper(%s), %s, %s, %s)
        ON DUPLICATE KEY UPDATE blockchain = upper(%s), symbol = %s, regUser = %s
        """

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(update_query, (blockchain, keyword, symbol, reg_user, blockchain, symbol, reg_user,))
                conn.commit()

bot = commands.Bot(command_prefix=f"{command_flag}", intents=discord.Intents.all())
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
async def mint(ctx, *, arg="today"):
    if arg == "today":
        target_date = datetime.datetime.now()

        today = target_date
        tomorrow = target_date + datetime.timedelta(days=1)
        today_string = today.strftime("%Y-%m-%d %H:%M")
        tomorrow_string = tomorrow.strftime("%Y-%m-%d")
    else:
        try:
            target_date = datetime.datetime.strptime(arg, "%Y%m%d").date()

            today = target_date
            tomorrow = target_date + datetime.timedelta(days=1)
            today_string = today.strftime("%Y-%m-%d")
            tomorrow_string = tomorrow.strftime("%Y-%m-%d")
        except ValueError:
            await ctx.reply("```❌ Invalid date format. Please try again. (yyyymmdd)\n\n잘못된 날짜 형식입니다. 다시 시도해주세요. (yyyymmdd)```", mention_author=True)
            return

    buttonView = ButtonView(ctx, db, "")
    pages = []
    projects = Queries.select_all_projects(db, today_string, tomorrow_string) # removed the if-else statement and only use select_all_projects method
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
                    list_massage = list_massage + f"""\n\n"""
                    before_date = item_date
                    before_time = ""
                if before_time != item_time:
                    if before_time != "":
                        list_massage = list_massage + "\n"
                    list_massage = list_massage + f"""<t:{int(item['unixMintDate'])}>\n"""
                    before_time = item_time
                list_massage = list_massage + f"""> [{item['name']}]({item['twitterUrl']})  /  Supply: {item['supply']}  / WL: {item['wlPrice']} {item['blockchain']}  /  Public: {item['pubPrice']} {item['blockchain']}\n"""
                # print(len(list_massage))
            list_massage = list_massage + ""
        else:
            # update_channel = await bot.fetch_channel(1089590412164993044)
            # mention_string = update_channel.mention
            list_massage = list_massage + f"❌ No projects have been recommend.\nPlease press `!mup @twitter_handle` for the project you want to recommend.\n\n❌ 추천한 프로젝트가 없습니다.\n추천할 프로젝트는 `!mup @twitter_handle`을 눌러주세요."
            embed=discord.Embed(title="", description="")
            embed.add_field(name="", value=list_massage, inline=True)
            await ctx.reply(embed=embed, mention_author=True)
            return
    except Exception as e:
        print("Error:", e)
        return

    embed.add_field(name="", value=list_massage, inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def you(ctx, dc_id):
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

        today = datetime.datetime.now().date()
        today_string = today.strftime("%Y-%m-%d")
        tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).date()
        tomorrow_string = tomorrow.strftime("%Y-%m-%d")

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
                    list_massage = list_massage + f"""\n\n"""
                    before_date = item_date
                    before_time = ""
                if before_time != item_time:
                    if before_time != "":
                        list_massage = list_massage + "\n"
                    list_massage = list_massage + f"""<t:{int(item['unixMintDate'])}>\n"""
                    before_time = item_time
                list_massage = list_massage + f"""> [{item['name']}]({item['twitterUrl']})  /  Supply: {item['supply']}  / WL: {item['wlPrice']} {item['blockchain']}  /  Public: {item['pubPrice']} {item['blockchain']}\n"""
                # print(len(list_massage))
            list_massage = list_massage + ""
        else:
            list_massage = list_massage + f"❌ `{regUser}` has no recommended project.\n\n`❌ {regUser}`가 추천한 프로젝트는 없습니다."
            embed=discord.Embed(title="", description="")
            embed.add_field(name="", value=list_massage, inline=True)
            await ctx.reply(embed=embed, mention_author=True)
            return
    except Exception as e:
        print("Error:", e)
        return

    embed.add_field(name="", value=list_massage, inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def msearch(ctx, *, project_name):
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
        embed=discord.Embed(title="", description="")
        embed.add_field(name="", value=f"❌ No projects have been searched as `{project_name}`.\nPlease search for another word.\n\n❌ `{project_name}`(으)로 검색된 프로젝트가 없습니다.\n다른 단어를 검색하십시오.", inline=True)
        await ctx.reply(embed=embed, mention_author=True)

@bot.command()
async def mrank(ctx):
    results = Queries.select_ranking(db)

    num_pages = (len(results) + 9) // 10

    pages = []

    for page in range(num_pages):
        embed = Embed(title=f"Top {page * 10 + 1} ~ {page * 10 + 10} Rank\n", color=0x00ff00)

        for i in range(10):
            index = page * 10 + i
            if index >= len(results):
                break

            item = results[index]
            link_url = f"[Twitter]({item['twitterUrl']})"
            if item['discordUrl']:
                link_url = f"{link_url}  |  [Discord]({item['discordUrl']})"
            if item['walletCheckerUrl']:
                link_url = f"{link_url}  |  [Checker]({item['walletCheckerUrl']})"

            field_name = f"`{item['ranking']}.` {item['name']} :thumbsup: {item['up_score']}  :thumbsdown: {item['down_score']}"
            if item['mintDate'] == 'TBA':
                field_value = f"{item['mintDate']}  |  {link_url}"
            else:
                field_value = f"<t:{int(item['unixMintDate'])}>  |  {link_url}"
            embed.add_field(name=field_name, value=field_value, inline=False)
            embed.set_footer(text=f"by SearchFI Bot")

        cal = Page(content=f"**🏆 Project Ranking Top 50 🏆**", embed=embed)
        pages.append(cal)

    paginator = Paginator(bot)
    await paginator.send(ctx.channel, pages, type=NavigationType.Buttons)

@bot.command()
async def mreg(ctx):
    embed=discord.Embed(title="", description="")
    embed.add_field(name="", value="ℹ️ Please register the project with the button below.\n\nℹ️ 아래 버튼으로 프로젝트를 등록해주세요.", inline=True)
    await ctx.reply(embed=embed, mention_author=True)

    button_url = f'https://discord.com/api/oauth2/authorize?client_id={discord_client_id}&redirect_uri={quote(f"{bot_domain}/discord-callback/register")}&response_type=code&scope=identify'
    button = discord.ui.Button(style=discord.ButtonStyle.green, label="Go to Registration", url=button_url)
    view = discord.ui.View()
    view.add_item(button)
    await ctx.send(view=view)

@bot.command()
async def mmod(ctx):
    embed=discord.Embed(title="", description="")
    embed.add_field(name="", value="ℹ️ Please correct the project with the button below.\n\nℹ️ 아래 버튼으로 프로젝트를 수정해주세요.", inline=True)
    await ctx.reply(embed=embed, mention_author=True)

    button_url = f'https://discord.com/api/oauth2/authorize?client_id={discord_client_id}&redirect_uri={quote(f"{bot_domain}/discord-callback/modify")}&response_type=code&scope=identify'
    button = discord.ui.Button(style=discord.ButtonStyle.red, label="Go to Modify", url=button_url)
    view = discord.ui.View()
    view.add_item(button)
    await ctx.send(view=view)

@bot.command()
async def mup(ctx, *, twitter_handle: str):
    user_id = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"

    project_info = Queries.get_project_id_by_twitter_handle(db, twitter_handle)

    embed=discord.Embed(title="", description="")

    if project_info is None:
        embed.add_field(name="", value=f"❌ No project found for `{twitter_handle}`.\n Click `!mreg` to register the project.\n\n❌ `{twitter_handle}`에 대한 프로젝트를 찾을 수 없습니다.\n `!mreg`를 눌러서 프로젝트를 등록해주세요.", inline=True)
        await ctx.reply(embed=embed, mention_author=True)

        button_url = f'https://discord.com/api/oauth2/authorize?client_id={discord_client_id}&redirect_uri={quote(f"{bot_domain}/discord-callback/register")}&response_type=code&scope=identify'
        button = discord.ui.Button(style=discord.ButtonStyle.green, label="Go to Registration", url=button_url)
        view = discord.ui.View()
        view.add_item(button)
        await ctx.send(view=view)

        return

    project_id = project_info['id']

    previous_recommendation = Queries.add_recommendation(db, project_id, user_id, "UP")

    if previous_recommendation is None:
        embed.add_field(name="", value=f"✅ Successfully recommended `{twitter_handle}` project!\n\n✅ `{twitter_handle}` 프로젝트를 추천했습니다!", inline=True)
    elif previous_recommendation == "UP":
        embed.add_field(name="", value=f"ℹ️ You have already recommended `{twitter_handle}` project.\n\nℹ️ 이미 `{twitter_handle}` 프로젝트를 추천하셨습니다.", inline=True)
    else:
        embed.add_field(name="", value=f":thumbup: Changed your downvote to an upvote for `{twitter_handle}` project!\n\n:thumbup: `{twitter_handle}` 프로젝트에 대한 비추천을 추천으로 변경했습니다!", inline=True)

    await ctx.reply(embed=embed, mention_author=True)

@bot.command()
async def mdown(ctx, *, twitter_handle: str):
    user_id = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"

    project_info = Queries.get_project_id_by_twitter_handle(db, twitter_handle)

    embed=discord.Embed(title="", description="")

    if project_info is None:
        embed.add_field(name="", value=f"❌ No project found for `{twitter_handle}`.\n Click `!mreg` to register the project.\n\n❌ `{twitter_handle}`에 대한 프로젝트를 찾을 수 없습니다.\n `!mreg`를 눌러서 프로젝트를 등록해주세요.", inline=True)
        await ctx.reply(embed=embed, mention_author=True)

        button_url = f'https://discord.com/api/oauth2/authorize?client_id={discord_client_id}&redirect_uri={quote(f"{bot_domain}/discord-callback/register")}&response_type=code&scope=identify'
        button = discord.ui.Button(style=discord.ButtonStyle.green, label="Go to Registration", url=button_url)
        view = discord.ui.View()
        view.add_item(button)
        await ctx.send(view=view)

        return

    project_id = project_info['id']

    previous_recommendation = Queries.add_recommendation(db, project_id, user_id, "DOWN")

    if previous_recommendation is None:
        embed.add_field(name="", value=f"❌ Successfully downvoted `{twitter_handle}` project!\n\n❌ `{twitter_handle}` 프로젝트를 비추천했습니다!", inline=True)
    elif previous_recommendation == "DOWN":
        embed.add_field(name="", value=f"ℹ️ You have already downvoted `{twitter_handle}` project.\n\nℹ️ 이미 `{twitter_handle}` 프로젝트를 비추천하셨습니다.", inline=True)
    else:
        embed.add_field(name="", value=f":thumbdown: Changed your upvote to a downvote for `{twitter_handle}` project!\n\n:thumbdown: `{twitter_handle}` 프로젝트에 대한 추천을 비추천으로 변경했습니다!", inline=True)

    await ctx.reply(embed=embed, mention_author=True)

@bot.command()
async def myrank(ctx, *, dc_id=None):
    if dc_id == None:
        user_id = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"
    else:
        print(dc_id[2:-1])
        user = await bot.fetch_user(dc_id[2:-1])
        print(user)
        if user is not None:
            print(f"이름: {user.name}")
            print(f"디스크리미네이터: {user.discriminator}")
            user_id = user.name + "#" + user.discriminator
        else:
            user_id = dc_id

    buttonView = ButtonView(ctx, db, "")
    results = Queries.select_my_ranking(db, user_id)

    num_pages = (len(results) + 9) // 10

    pages = []

    if num_pages > 0:
        for page in range(num_pages):
            embed = Embed(title="", color=0x0061ff)

            for i in range(10):
                index = page * 10 + i
                if index >= len(results):
                    break

                item = results[index]
                link_url = f"[Twitter]({item['twitterUrl']})"
                if item['discordUrl']:
                    link_url = f"{link_url}  |  [Discord]({item['discordUrl']})"
                if item['walletCheckerUrl']:
                    link_url = f"{link_url}  |  [Checker]({item['walletCheckerUrl']})"

                field_name = f"`{item['ranking']}.` {item['name']} :thumbsup: {item['up_score']}  :thumbsdown: {item['down_score']}"
                if item['mintDate'] == 'TBA':
                    field_value = f"{item['mintDate']}  |  {link_url}"
                else:
                    field_value = f"<t:{int(item['unixMintDate'])}>  |  {link_url}"
                embed.add_field(name=field_name, value=field_value, inline=False)

            try:
                avatar_url = await buttonView.get_member_avatar(user_id.split('#')[0], user_id.split('#')[1])
                if avatar_url == None:
                    avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
            except Exception as e:
                avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
            embed.set_author(name=f"{user_id}\n Total {len(results)} Project in Top 50 rank", icon_url=f"{avatar_url}")
            embed.set_thumbnail(url=avatar_url)
            embed.set_footer(text=f"by SearchFI Bot")

            cal = Page(content=f"", embed=embed)
            pages.append(cal)
    else:
        embed = Embed(title="", color=0x0061ff)
        try:
            avatar_url = await buttonView.get_member_avatar(user_id.split('#')[0], user_id.split('#')[1])
            if avatar_url == None:
                avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
        except Exception as e:
            avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
        embed.set_author(name=f"{user_id}\n Total {len(results)} Project in Top 50 rank", icon_url=f"{avatar_url}")
        embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text=f"by SearchFI Bot")

        cal = Page(content=f"", embed=embed)
        pages.append(cal)

    paginator = Paginator(bot)
    await paginator.send(ctx.channel, pages, type=NavigationType.Buttons)

@bot.command()
async def myup(ctx, *, dc_id=None):
    if dc_id == None:
        user_id = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"
    else:
        print(dc_id[2:-1])
        user = await bot.fetch_user(dc_id[2:-1])
        print(user)
        if user is not None:
            print(f"이름: {user.name}")
            print(f"디스크리미네이터: {user.discriminator}")
            user_id = user.name + "#" + user.discriminator
        else:
            user_id = dc_id

    buttonView = ButtonView(ctx, db, "")
    results = Queries.select_my_updown(db, user_id, 'UP')

    num_pages = (len(results) + 9) // 10

    pages = []

    if num_pages > 0:
        for page in range(num_pages):
            embed = Embed(title="", color=0x0061ff)

            for i in range(10):
                index = page * 10 + i
                if index >= len(results):
                    break

                item = results[index]
                link_url = f"[Twitter]({item['twitterUrl']})"
                if item['discordUrl']:
                    link_url = f"{link_url}  |  [Discord]({item['discordUrl']})"
                if item['walletCheckerUrl']:
                    link_url = f"{link_url}  |  [Checker]({item['walletCheckerUrl']})"

                field_name = f"`{item['ranking']}.` {item['name']} :thumbsup: {item['up_score']}  :thumbsdown: {item['down_score']}"
                if item['mintDate'] == 'TBA':
                    field_value = f"{item['mintDate']}  |  {link_url}"
                else:
                    field_value = f"<t:{int(item['unixMintDate'])}>  |  {link_url}"
                embed.add_field(name=field_name, value=field_value, inline=False)

            try:
                avatar_url = await buttonView.get_member_avatar(user_id.split('#')[0], user_id.split('#')[1])
                if avatar_url == None:
                    avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
            except Exception as e:
                avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
            embed.set_author(name=f"{user_id}\n Total {len(results)} Project in Top 50 rank", icon_url=f"{avatar_url}")
            embed.set_thumbnail(url=avatar_url)
            embed.set_footer(text=f"by SearchFI Bot")

            cal = Page(content=f"", embed=embed)
            pages.append(cal)
    else:
        embed = Embed(title="", color=0x0061ff)
        try:
            avatar_url = await buttonView.get_member_avatar(user_id.split('#')[0], user_id.split('#')[1])
            if avatar_url == None:
                avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
        except Exception as e:
            avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
        embed.set_author(name=f"{user_id}\n Total {len(results)} UP", icon_url=f"{avatar_url}")
        embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text=f"by SearchFI Bot")

        cal = Page(content=f"", embed=embed)
        pages.append(cal)

    paginator = Paginator(bot)
    await paginator.send(ctx.channel, pages, type=NavigationType.Buttons)

@bot.command()
async def mydown(ctx, *, dc_id=None):
    if dc_id == None:
        user_id = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"
    else:
        print(dc_id[2:-1])
        user = await bot.fetch_user(dc_id[2:-1])
        print(user)
        if user is not None:
            print(f"이름: {user.name}")
            print(f"디스크리미네이터: {user.discriminator}")
            user_id = user.name + "#" + user.discriminator
        else:
            user_id = dc_id

    buttonView = ButtonView(ctx, db, "")
    results = Queries.select_my_updown(db, user_id, 'DOWN')

    num_pages = (len(results) + 9) // 10

    pages = []

    if num_pages > 0:
        for page in range(num_pages):
            embed = Embed(title="", color=0x0061ff)

            for i in range(10):
                index = page * 10 + i
                if index >= len(results):
                    break

                item = results[index]
                link_url = f"[Twitter]({item['twitterUrl']})"
                if item['discordUrl']:
                    link_url = f"{link_url}  |  [Discord]({item['discordUrl']})"
                if item['walletCheckerUrl']:
                    link_url = f"{link_url}  |  [Checker]({item['walletCheckerUrl']})"

                field_name = f"`{item['ranking']}.` {item['name']} :thumbsup: {item['up_score']}  :thumbsdown: {item['down_score']}"
                if item['mintDate'] == 'TBA':
                    field_value = f"{item['mintDate']}  |  {link_url}"
                else:
                    field_value = f"<t:{int(item['unixMintDate'])}>  |  {link_url}"
                embed.add_field(name=field_name, value=field_value, inline=False)

            try:
                avatar_url = await buttonView.get_member_avatar(user_id.split('#')[0], user_id.split('#')[1])
                if avatar_url == None:
                    avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
            except Exception as e:
                avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
            embed.set_author(name=f"{user_id}\n Total {len(results)} Project in Top 50 rank", icon_url=f"{avatar_url}")
            embed.set_thumbnail(url=avatar_url)
            embed.set_footer(text=f"by SearchFI Bot")

            cal = Page(content=f"", embed=embed)
            pages.append(cal)
    else:
        embed = Embed(title="", color=0x0061ff)
        try:
            avatar_url = await buttonView.get_member_avatar(user_id.split('#')[0], user_id.split('#')[1])
            if avatar_url == None:
                avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
        except Exception as e:
            avatar_url = "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
        embed.set_author(name=f"{user_id}\n Total {len(results)} UP", icon_url=f"{avatar_url}")
        embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text=f"by SearchFI Bot")

        cal = Page(content=f"", embed=embed)
        pages.append(cal)

    paginator = Paginator(bot)
    await paginator.send(ctx.channel, pages, type=NavigationType.Buttons)

@bot.command()
@commands.has_any_role('SF.Team', 'SF.Super', 'SF.Pioneer')
async def mchecker(ctx, twitter_handle: str = None, wallet_checker_url: str = None):
    if twitter_handle is None or wallet_checker_url is None:
        await ctx.reply("Usage: `!mchecker <Twitter_Handle> <Wallet_Checker_URL>`", mention_author=True)
        return

    # Validate the URL
    parsed_url = urlparse(wallet_checker_url)
    if not parsed_url.scheme or not parsed_url.netloc:
        await ctx.reply(f"Please enter a `{wallet_checker_url}` valid URL format.", mention_author=True)
        return

    # Find the project ID using the Twitter handle
    project_info = Queries.get_project_id_by_twitter_handle(db, twitter_handle)

    if project_info is None:
        await ctx.reply(f"Cannot find a project corresponding to `{twitter_handle}`.\n\n`{twitter_handle}`에 해당하는 프로젝트를 찾을 수 없습니다.", mention_author=True)
        return

    project_id = project_info['id']

    # Update the Wallet Checker URL
    Queries.update_wallet_checker_url(db, project_id, wallet_checker_url)

    await ctx.reply(f"Wallet Checker URL for the `{twitter_handle}` project has been updated!\n\n`{twitter_handle}` 프로젝트의 Wallet Checker URL이 업데이트되었습니다!", mention_author=True)

@bot.command()
@commands.has_any_role('SF.Team', 'SF.Super')
async def mt(ctx, blockchain: str = "ETH", tier_url: str = None):
    user_id = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"

    if tier_url:
        Queries.update_tier_url(db, blockchain, tier_url, user_id)
    result = Queries.get_tier_by_blockchain(db, blockchain)
    await ctx.reply(f"{result['imageUrl']}", mention_author=True)

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

async def me_btc(ctx, symbol):
    # scraper = cloudscraper.create_scraper(delay=10, browser="chrome")
    scraper = cfscrape.create_scraper()
    headers = {
        "Cookie":"rl_page_init_referrer=RudderEncrypt%3AU2FsdGVkX19SmdvYXC8KilD32raXT2vP87SmiQKFg5Y%3D; rl_page_init_referring_domain=RudderEncrypt%3AU2FsdGVkX1%2Bkn8NEloAGklP49YLEO4H60rYZihLETF8%3D; _gcl_au=1.1.229430566.1681143900; rs_ga=GA1.1.0eb551a7-c5a9-42c1-9e56-f348cc105645; intercom-id-htawnd0o=b1c10552-c81c-4245-9b1e-1c43fabbef15; intercom-device-id-htawnd0o=74e588ef-f3b0-4736-afe0-a85dc01acf02; _ga=GA1.2.236944940.1681143904; _ga_ED223BN325=GS1.1.1681144184.1.1.1681144223.21.0.0; __stripe_mid=4dafe4a9-0000-491b-884c-1b9852e4ba41375aca; session_ids=%7B%22ids%22%3A%5B%7B%22signature%22%3A%22k3v7UCKisdgoSfLLcko1hrzR_NIaT8A0h80vHuoFGbs%22%2C%22walletAddress%22%3A%220xa1B1ec6eaD8CEfa028Df12609F38EEDAc356a697%22%7D%2C%7B%22signature%22%3A%22apnsUJJbccuhKvDQlgjHmh7nlVLeRe19jsA8iOj_dyU%22%2C%22walletAddress%22%3A%220x21a79af2e2f0b8310AAE1865F301746F39E93f1e%22%7D%2C%7B%22signature%22%3A%22BmObApHtyKvxjNQwUVYjAKs1YsQ1u9Ja13_C77WQarw%22%2C%22walletAddress%22%3A%220x9936a60E3883889aF8f2Bc4EA9A0436548E8f57C%22%7D%5D%7D; session_id=BmObApHtyKvxjNQwUVYjAKs1YsQ1u9Ja13_C77WQarw; intercom-session-htawnd0o=; _gid=GA1.2.212248876.1685652374; _cfuvid=SAxej90x8eRcQOO4qy_hUhwcnGfwmquwjfrq4kooSXY-1685705944312-0-604800000; rl_group_id=RudderEncrypt%3AU2FsdGVkX1%2FM%2BPRqsGdil54MSzbSifD1llRjViuC1y8%3D; rl_group_trait=RudderEncrypt%3AU2FsdGVkX19F0TEblRrmeO3asO%2FADly5lDgr1cUqQrQ%3D; rl_anonymous_id=RudderEncrypt%3AU2FsdGVkX1%2FBw41TW%2B36K4h9yhPpXsN%2BmsG2W2zZv%2BYBVQI9IZd1NMAraCyIvLN5juRIM71cCvh%2BgLwN990wiw%3D%3D; rs_ga_8BCG117VGT=GS1.1.1685740263222.55.1.1685742625.58.0.0; rl_user_id=RudderEncrypt%3AU2FsdGVkX19aw%2BhVu4EeNA01tWeq4VSGFPjXvuAONXrMsy4oIPwKA9TL9aydLL0mYsIija0cSLwu7PdjLKXLJw%3D%3D; rl_trait=RudderEncrypt%3AU2FsdGVkX1%2FBdtUkP5J1nWEMCEVEDTlbW4f1VV70gnxm0oYxHN7KL25fmsuoUmKXL7lzS3jXpNwVa7IOWAEz%2FPfzCqFg%2B1ZSU29TW8Uxlw6cKF5F0f7DeJOXGXIo4ZP3Pt06z2Qow%2B0O%2FD95Aqft81tpXsnPx6fbSBCBLV9oV0B6T9o%2FjU4Rx%2FLe4AoG8Gr%2F9d%2Fh1KeAcQJkAsDHkFXG5VRctROK4wLSgkd90pXIiBlcJHsSJIl4CIv77WPF6Xf4op%2F94rlpvOWvAwW3GknDrQ%3D%3D; rl_session=RudderEncrypt%3AU2FsdGVkX1%2BT%2F0uvs%2B5IOYIdJP7IOg3HKd9xR0qDjsliV2QvP%2BwCrp9Paciy0EO6oKFAD%2FvmzdOT%2BRy8Ttez0fP2Er6fk05BclAGh240PrpHCr8yTWwHVmOuFtvJHMbyFWwDaO%2FB%2FGvyKVS06e9P%2BQ%3D%3D; datadome=42FXdKetE3WqM1ZCRKPbjI9N8NLTI4~ud1cM0onKpIgjgEtCavL3zJfh-rX6yFquKpEftEOMFb~D2CjSbVROmGIWGW50pKMqXkygkgW21a6sMJvG07T~3BYRiIhV~bnK; __cf_bm=b7xaTzxkAyHtkoGcTNEj5B5GARCxq2_ZnCb77h72Bm4-1685744647-0-AfBFIvVtHFijJGQYEjv/n8RTWhW716qI0zRVkYGAkV79zQuz3mGhkPQTrmS80EFFcf8lFixw3RQz+c5TXE4gtOLbZHe69bNkPgR+S/s/Nm0E6x5LD138pdGoy/EV8vofyqoPEKVhyZ7odLUXZBi6zS8=; mp_e07f9907b6792861d8448bc4004fb2b4_mixpanel=%7B%22distinct_id%22%3A%20%221876bfc289b1bd8-0a3c2363de8f04-1d525634-1d03d0-1876bfc289c2b17%22%2C%22%24device_id%22%3A%20%221876bfc289b1bd8-0a3c2363de8f04-1d525634-1d03d0-1876bfc289c2b17%22%2C%22%24initial_referrer%22%3A%20%22https%3A%2F%2Ft.co%2F%22%2C%22%24initial_referring_domain%22%3A%20%22t.co%22%7D",
        "User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36"
    }
    response = scraper.get(f"https://api-mainnet.magiceden.io/v2/ord/btc/collections/{symbol}", headers=headers).text
    data = json.loads(response)

    projectName = data["name"]
    projectImg = data['imageURI']
    projectChain = data['chain'].upper()
    projectTwitter = data['twitterLink']
    projectDiscord = data['discordLink']
    projectWebsite = data['websiteLink']
    projectLinks = f"[MegicEden](https://magiceden.io/ordinals/marketplace/{symbol})"
    if projectWebsite:
        projectLinks += f" | [Website]({projectWebsite})"
    if projectDiscord:
        projectLinks += f" | [Discord]({projectDiscord})"
    if projectTwitter:
        projectLinks += f" | [Twitter]({projectTwitter})"

    response = scraper.get(f"https://api-mainnet.magiceden.io/v2/ord/btc/stat?collectionSymbol={symbol}", headers=headers).text
    data = json.loads(response)
    projectFloorPrice = float(data['floorPrice']) / 100000000
    projectSupply = data['supply']
    projectOwners = data['owners']

    embed = Embed(title=f"{projectName}", color=0xbc2467, url=f"https://magiceden.io/ordinals/marketplace/{symbol}")
    embed.set_thumbnail(url=f"{projectImg}")
    embed.add_field(name=f"""Floor""", value=f"```{projectFloorPrice} {projectChain}     ```""", inline=True)
    embed.add_field(name=f"""Supply""", value=f"```{projectSupply}       ```", inline=True)
    embed.add_field(name=f"""Owners""", value=f"```{projectOwners}       ```", inline=True)
    embed.add_field(name=f"""Links""", value=f"{projectLinks}", inline=True)
    embed.set_footer(text="Powered by 으노아부지#2642")

    await ctx.reply(embed=embed, mention_author=True)

async def me_sol(ctx, symbol):
    # scraper = cloudscraper.create_scraper(delay=10, browser="chrome")
    scraper = cfscrape.create_scraper()
    headers = {
        "Cookie":"rl_page_init_referrer=RudderEncrypt%3AU2FsdGVkX19SmdvYXC8KilD32raXT2vP87SmiQKFg5Y%3D; rl_page_init_referring_domain=RudderEncrypt%3AU2FsdGVkX1%2Bkn8NEloAGklP49YLEO4H60rYZihLETF8%3D; _gcl_au=1.1.229430566.1681143900; rs_ga=GA1.1.0eb551a7-c5a9-42c1-9e56-f348cc105645; intercom-id-htawnd0o=b1c10552-c81c-4245-9b1e-1c43fabbef15; intercom-device-id-htawnd0o=74e588ef-f3b0-4736-afe0-a85dc01acf02; _ga=GA1.2.236944940.1681143904; _ga_ED223BN325=GS1.1.1681144184.1.1.1681144223.21.0.0; __stripe_mid=4dafe4a9-0000-491b-884c-1b9852e4ba41375aca; session_ids=%7B%22ids%22%3A%5B%7B%22signature%22%3A%22k3v7UCKisdgoSfLLcko1hrzR_NIaT8A0h80vHuoFGbs%22%2C%22walletAddress%22%3A%220xa1B1ec6eaD8CEfa028Df12609F38EEDAc356a697%22%7D%2C%7B%22signature%22%3A%22apnsUJJbccuhKvDQlgjHmh7nlVLeRe19jsA8iOj_dyU%22%2C%22walletAddress%22%3A%220x21a79af2e2f0b8310AAE1865F301746F39E93f1e%22%7D%2C%7B%22signature%22%3A%22BmObApHtyKvxjNQwUVYjAKs1YsQ1u9Ja13_C77WQarw%22%2C%22walletAddress%22%3A%220x9936a60E3883889aF8f2Bc4EA9A0436548E8f57C%22%7D%5D%7D; session_id=BmObApHtyKvxjNQwUVYjAKs1YsQ1u9Ja13_C77WQarw; intercom-session-htawnd0o=; _gid=GA1.2.212248876.1685652374; _cfuvid=SAxej90x8eRcQOO4qy_hUhwcnGfwmquwjfrq4kooSXY-1685705944312-0-604800000; rl_group_id=RudderEncrypt%3AU2FsdGVkX1%2FM%2BPRqsGdil54MSzbSifD1llRjViuC1y8%3D; rl_group_trait=RudderEncrypt%3AU2FsdGVkX19F0TEblRrmeO3asO%2FADly5lDgr1cUqQrQ%3D; rl_anonymous_id=RudderEncrypt%3AU2FsdGVkX1%2FBw41TW%2B36K4h9yhPpXsN%2BmsG2W2zZv%2BYBVQI9IZd1NMAraCyIvLN5juRIM71cCvh%2BgLwN990wiw%3D%3D; rs_ga_8BCG117VGT=GS1.1.1685740263222.55.1.1685742625.58.0.0; rl_user_id=RudderEncrypt%3AU2FsdGVkX19aw%2BhVu4EeNA01tWeq4VSGFPjXvuAONXrMsy4oIPwKA9TL9aydLL0mYsIija0cSLwu7PdjLKXLJw%3D%3D; rl_trait=RudderEncrypt%3AU2FsdGVkX1%2FBdtUkP5J1nWEMCEVEDTlbW4f1VV70gnxm0oYxHN7KL25fmsuoUmKXL7lzS3jXpNwVa7IOWAEz%2FPfzCqFg%2B1ZSU29TW8Uxlw6cKF5F0f7DeJOXGXIo4ZP3Pt06z2Qow%2B0O%2FD95Aqft81tpXsnPx6fbSBCBLV9oV0B6T9o%2FjU4Rx%2FLe4AoG8Gr%2F9d%2Fh1KeAcQJkAsDHkFXG5VRctROK4wLSgkd90pXIiBlcJHsSJIl4CIv77WPF6Xf4op%2F94rlpvOWvAwW3GknDrQ%3D%3D; rl_session=RudderEncrypt%3AU2FsdGVkX1%2BT%2F0uvs%2B5IOYIdJP7IOg3HKd9xR0qDjsliV2QvP%2BwCrp9Paciy0EO6oKFAD%2FvmzdOT%2BRy8Ttez0fP2Er6fk05BclAGh240PrpHCr8yTWwHVmOuFtvJHMbyFWwDaO%2FB%2FGvyKVS06e9P%2BQ%3D%3D; datadome=42FXdKetE3WqM1ZCRKPbjI9N8NLTI4~ud1cM0onKpIgjgEtCavL3zJfh-rX6yFquKpEftEOMFb~D2CjSbVROmGIWGW50pKMqXkygkgW21a6sMJvG07T~3BYRiIhV~bnK; __cf_bm=b7xaTzxkAyHtkoGcTNEj5B5GARCxq2_ZnCb77h72Bm4-1685744647-0-AfBFIvVtHFijJGQYEjv/n8RTWhW716qI0zRVkYGAkV79zQuz3mGhkPQTrmS80EFFcf8lFixw3RQz+c5TXE4gtOLbZHe69bNkPgR+S/s/Nm0E6x5LD138pdGoy/EV8vofyqoPEKVhyZ7odLUXZBi6zS8=; mp_e07f9907b6792861d8448bc4004fb2b4_mixpanel=%7B%22distinct_id%22%3A%20%221876bfc289b1bd8-0a3c2363de8f04-1d525634-1d03d0-1876bfc289c2b17%22%2C%22%24device_id%22%3A%20%221876bfc289b1bd8-0a3c2363de8f04-1d525634-1d03d0-1876bfc289c2b17%22%2C%22%24initial_referrer%22%3A%20%22https%3A%2F%2Ft.co%2F%22%2C%22%24initial_referring_domain%22%3A%20%22t.co%22%7D",
        "User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36"
    }

    response = scraper.get(f"https://api-mainnet.magiceden.io/collections/{symbol}?edge_cache=true", headers=headers).text
    data = json.loads(response)

    projectName = data["name"]
    projectImg = data['image']
    projectChain = 'SOL'
    projectTwitter = data['twitter']
    projectDiscord = data['discord']
    projectWebsite = data['website']
    projectLinks = f"[MegicEden](https://magiceden.io/ko/marketplace/{symbol})"
    if projectWebsite:
        projectLinks += f" | [Website]({projectWebsite})"
    if projectDiscord:
        projectLinks += f" | [Discord]({projectDiscord})"
    if projectTwitter:
        projectLinks += f" | [Twitter]({projectTwitter})"

    response = scraper.get(f"https://api-mainnet.magiceden.io/rpc/getCollectionEscrowStats/{symbol}?edge_cache=true", headers=headers).text
    results = json.loads(response)
    data = results['results']
    projectFloorPrice = float(data['floorPrice']) / 1000000000

    response = scraper.get(f"https://api-mainnet.magiceden.io/rpc/getCollectionHolderStats/{symbol}?edge_cache=true&agg=2", headers=headers).text
    results = json.loads(response)
    data = results['results']
    projectSupply = data['totalSupply']
    projectOwners = data['uniqueHolders']

    embed = Embed(title=f"{projectName}", color=0xbc2467, url=f"https://magiceden.io/ko/marketplace/{symbol}")
    embed.set_thumbnail(url=f"{projectImg}")
    embed.add_field(name=f"""Floor""", value=f"```{projectFloorPrice} {projectChain}     ```""", inline=True)
    embed.add_field(name=f"""Supply""", value=f"```{projectSupply}       ```", inline=True)
    embed.add_field(name=f"""Owners""", value=f"```{projectOwners}       ```", inline=True)
    embed.add_field(name=f"""Links""", value=f"{projectLinks}", inline=True)
    embed.set_footer(text="Powered by 으노아부지#2642")

    await ctx.reply(embed=embed, mention_author=True)

async def me_matic(ctx, symbol):
    # scraper = cloudscraper.create_scraper(delay=10, browser="chrome")
    scraper = cfscrape.create_scraper()
    headers = {
        "Cookie":"rl_page_init_referrer=RudderEncrypt%3AU2FsdGVkX19SmdvYXC8KilD32raXT2vP87SmiQKFg5Y%3D; rl_page_init_referring_domain=RudderEncrypt%3AU2FsdGVkX1%2Bkn8NEloAGklP49YLEO4H60rYZihLETF8%3D; _gcl_au=1.1.229430566.1681143900; rs_ga=GA1.1.0eb551a7-c5a9-42c1-9e56-f348cc105645; intercom-id-htawnd0o=b1c10552-c81c-4245-9b1e-1c43fabbef15; intercom-device-id-htawnd0o=74e588ef-f3b0-4736-afe0-a85dc01acf02; _ga=GA1.2.236944940.1681143904; _ga_ED223BN325=GS1.1.1681144184.1.1.1681144223.21.0.0; __stripe_mid=4dafe4a9-0000-491b-884c-1b9852e4ba41375aca; session_ids=%7B%22ids%22%3A%5B%7B%22signature%22%3A%22k3v7UCKisdgoSfLLcko1hrzR_NIaT8A0h80vHuoFGbs%22%2C%22walletAddress%22%3A%220xa1B1ec6eaD8CEfa028Df12609F38EEDAc356a697%22%7D%2C%7B%22signature%22%3A%22apnsUJJbccuhKvDQlgjHmh7nlVLeRe19jsA8iOj_dyU%22%2C%22walletAddress%22%3A%220x21a79af2e2f0b8310AAE1865F301746F39E93f1e%22%7D%2C%7B%22signature%22%3A%22BmObApHtyKvxjNQwUVYjAKs1YsQ1u9Ja13_C77WQarw%22%2C%22walletAddress%22%3A%220x9936a60E3883889aF8f2Bc4EA9A0436548E8f57C%22%7D%5D%7D; session_id=BmObApHtyKvxjNQwUVYjAKs1YsQ1u9Ja13_C77WQarw; intercom-session-htawnd0o=; _gid=GA1.2.212248876.1685652374; _cfuvid=SAxej90x8eRcQOO4qy_hUhwcnGfwmquwjfrq4kooSXY-1685705944312-0-604800000; rl_group_id=RudderEncrypt%3AU2FsdGVkX1%2FM%2BPRqsGdil54MSzbSifD1llRjViuC1y8%3D; rl_group_trait=RudderEncrypt%3AU2FsdGVkX19F0TEblRrmeO3asO%2FADly5lDgr1cUqQrQ%3D; rl_anonymous_id=RudderEncrypt%3AU2FsdGVkX1%2FBw41TW%2B36K4h9yhPpXsN%2BmsG2W2zZv%2BYBVQI9IZd1NMAraCyIvLN5juRIM71cCvh%2BgLwN990wiw%3D%3D; rs_ga_8BCG117VGT=GS1.1.1685740263222.55.1.1685742625.58.0.0; rl_user_id=RudderEncrypt%3AU2FsdGVkX19aw%2BhVu4EeNA01tWeq4VSGFPjXvuAONXrMsy4oIPwKA9TL9aydLL0mYsIija0cSLwu7PdjLKXLJw%3D%3D; rl_trait=RudderEncrypt%3AU2FsdGVkX1%2FBdtUkP5J1nWEMCEVEDTlbW4f1VV70gnxm0oYxHN7KL25fmsuoUmKXL7lzS3jXpNwVa7IOWAEz%2FPfzCqFg%2B1ZSU29TW8Uxlw6cKF5F0f7DeJOXGXIo4ZP3Pt06z2Qow%2B0O%2FD95Aqft81tpXsnPx6fbSBCBLV9oV0B6T9o%2FjU4Rx%2FLe4AoG8Gr%2F9d%2Fh1KeAcQJkAsDHkFXG5VRctROK4wLSgkd90pXIiBlcJHsSJIl4CIv77WPF6Xf4op%2F94rlpvOWvAwW3GknDrQ%3D%3D; rl_session=RudderEncrypt%3AU2FsdGVkX1%2BT%2F0uvs%2B5IOYIdJP7IOg3HKd9xR0qDjsliV2QvP%2BwCrp9Paciy0EO6oKFAD%2FvmzdOT%2BRy8Ttez0fP2Er6fk05BclAGh240PrpHCr8yTWwHVmOuFtvJHMbyFWwDaO%2FB%2FGvyKVS06e9P%2BQ%3D%3D; datadome=42FXdKetE3WqM1ZCRKPbjI9N8NLTI4~ud1cM0onKpIgjgEtCavL3zJfh-rX6yFquKpEftEOMFb~D2CjSbVROmGIWGW50pKMqXkygkgW21a6sMJvG07T~3BYRiIhV~bnK; __cf_bm=b7xaTzxkAyHtkoGcTNEj5B5GARCxq2_ZnCb77h72Bm4-1685744647-0-AfBFIvVtHFijJGQYEjv/n8RTWhW716qI0zRVkYGAkV79zQuz3mGhkPQTrmS80EFFcf8lFixw3RQz+c5TXE4gtOLbZHe69bNkPgR+S/s/Nm0E6x5LD138pdGoy/EV8vofyqoPEKVhyZ7odLUXZBi6zS8=; mp_e07f9907b6792861d8448bc4004fb2b4_mixpanel=%7B%22distinct_id%22%3A%20%221876bfc289b1bd8-0a3c2363de8f04-1d525634-1d03d0-1876bfc289c2b17%22%2C%22%24device_id%22%3A%20%221876bfc289b1bd8-0a3c2363de8f04-1d525634-1d03d0-1876bfc289c2b17%22%2C%22%24initial_referrer%22%3A%20%22https%3A%2F%2Ft.co%2F%22%2C%22%24initial_referring_domain%22%3A%20%22t.co%22%7D",
        "User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36"
    }
    response = scraper.get(f"https://polygon-api.magiceden.io/v2/xc/collections/polygon/{symbol}", headers=headers).text
    data = json.loads(response)

    projectName = data["name"]
    projectImg = data['media']
    projectChain = 'MATIC'
    projectTwitter = data['twitterLink']
    projectDiscord = data['discordLink']
    projectWebsite = data['websiteLink']
    projectLinks = f"[MegicEden](https://magiceden.io/ko/collections/polygon/{symbol})"
    if projectWebsite:
        projectLinks += f" | [Website]({projectWebsite})"
    if projectDiscord:
        projectLinks += f" | [Discord]({projectDiscord})"
    if projectTwitter:
        projectLinks += f" | [Twitter]({projectTwitter})"

    response = scraper.get(f"https://polygon-api.magiceden.io/v2/xc/collections/polygon/{symbol}/stats", headers=headers).text
    data = json.loads(response)
    projectFloorPrice = float(data['floorPrice']) / 1000000000000000000
    projectSupply = data['totalSupply']
    projectOwners = data['ownerCount']

    embed = Embed(title=f"{projectName}", color=0xbc2467, url=f"https://magiceden.io/ko/collections/polygon/{symbol}")
    embed.set_thumbnail(url=f"{projectImg}")
    embed.add_field(name=f"""Floor""", value=f"```{projectFloorPrice} {projectChain}     ```""", inline=True)
    embed.add_field(name=f"""Supply""", value=f"```{projectSupply}       ```", inline=True)
    embed.add_field(name=f"""Owners""", value=f"```{projectOwners}       ```", inline=True)
    embed.add_field(name=f"""Links""", value=f"{projectLinks}", inline=True)
    embed.set_footer(text="Powered by 으노아부지#2642")

    await ctx.reply(embed=embed, mention_author=True)

@bot.command()
async def 메(ctx, keyword):
    await me(ctx, keyword)

@bot.command()
async def me(ctx, keyword):
    result = Queries.select_keyword(db, keyword)
    print(result['blockchain'], result['symbol'])

    if result['blockchain'] == "BTC":
        await me_btc(ctx, result['symbol'])
    elif result['blockchain'] == "SOL":
        await me_sol(ctx, result['symbol'])
    elif result['blockchain'] == "MATIC":
        await me_matic(ctx, result['symbol'])

@bot.command()
async def msave(ctx, blockchain, keyword, symbol):
    reg_user = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"
    Queries.update_keyword(db, blockchain, keyword, symbol, reg_user)
    await ctx.reply(f"✅ Keyword `{keyword}` has been saved.\n\n✅ `{keyword}` 키워드가 저장되었습니다.", mention_author=True)

timezone_mapping = {tz: tz for tz in all_timezones}
# Common abbreviations
timezone_mapping.update({
    'UTC': 'UTC',
    'EST': 'US/Eastern',
    'EDT': 'US/Eastern',
    'CST': 'US/Central',
    'CDT': 'US/Central',
    'MST': 'US/Mountain',
    'MDT': 'US/Mountain',
    'PST': 'US/Pacific',
    'PDT': 'US/Pacific',
    'HST': 'US/Hawaii',
    'AKST': 'US/Alaska',
    'AKDT': 'US/Alaska',
    'AEST': 'Australia/Eastern',
    'AEDT': 'Australia/Eastern',
    'ACST': 'Australia/Central',
    'ACDT': 'Australia/Central',
    'AWST': 'Australia/West',
    'KST': 'Asia/Seoul',
    'JST': 'Asia/Tokyo',
    'CET': 'Europe/Central',
    'CEST': 'Europe/Central',
    'EET': 'Europe/Eastern',
    'EEST': 'Europe/Eastern',
    'WET': 'Europe/Western',
    'WEST': 'Europe/Western',
    # Add more if needed
})

@bot.command()
async def mtime(ctx, date_str, time_str, from_tz_param, to_tz_str_param):
    from_tz_str = timezone_mapping.get(from_tz_param.upper())
    to_tz_str = timezone_mapping.get(to_tz_str_param.upper())

    if not from_tz_str or not to_tz_str:
        await ctx.send("Invalid timezone provided")
        return

    from_tz = pytz.timezone(from_tz_str)
    to_tz = pytz.timezone(to_tz_str)

    datetime_str = date_str + ' ' + time_str

    try:
        datetime_obj = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
    except ValueError:
        await ctx.send("Invalid datetime format. Please use 'YYYY-MM-DD HH:MM'")
        return

    datetime_obj = from_tz.localize(datetime_obj)
    datetime_in_to_tz = datetime_obj.astimezone(to_tz)

    await ctx.reply(f"```{datetime_str}({from_tz_param.upper()})\n\n🔄\n\n{datetime_in_to_tz.strftime('%Y-%m-%d %H:%M')}({to_tz_str_param.upper()})```", mention_author=True)

bot.run(bot_token)

