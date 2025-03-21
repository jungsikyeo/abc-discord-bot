import asyncio
import datetime
import time
import pymysql
import discord
import requests
import os as operating_system
import random
import cloudscraper
import json
import pytz
import urllib3
import urllib
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import re
import gspread
import uuid
import io
import base64
import logging
import langid
import deepl
import numpy as np
from openai import OpenAI
from datetime import timezone
from pytz import all_timezones
from discord.ext import commands, tasks
from discord.commands import Option
from discord.commands.context import ApplicationContext
from discord import Embed
from discord.ui import View
from discord.ext.pages import Paginator
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB
from urllib.parse import quote, urlparse
from dotenv import load_dotenv
from matplotlib.dates import DateFormatter
from binance.client import Client
from datetime import timedelta
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image, ImageSequence
from langchain_openai import ChatOpenAI
from langchain.chains import LLMMathChain
from langchain.agents import Tool, initialize_agent, AgentType
from web3 import Web3

load_dotenv()

command_flag = operating_system.getenv("SEARCHFI_BOT_FLAG")
bot_token = operating_system.getenv("SEARCHFI_BOT_TOKEN")
mysql_ip = operating_system.getenv("MYSQL_IP")
mysql_port = operating_system.getenv("MYSQL_PORT")
mysql_id = operating_system.getenv("MYSQL_ID")
mysql_passwd = operating_system.getenv("MYSQL_PASSWD")
mysql_db = operating_system.getenv("MYSQL_DB")
bot_domain = operating_system.getenv("SEARCHFI_BOT_DOMAIN")
discord_client_id = operating_system.getenv("DISCORD_CLIENT_ID")
guild_ids = list(map(int, operating_system.getenv('GUILD_ID').split(',')))
bot_log_folder = operating_system.getenv("BOT_LOG_FOLDER")
deepl_api_key = operating_system.getenv("DEEPL_API_KEY")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(filename=f"{bot_log_folder}/alphabot2_bot.log", mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=operating_system.getenv("OPENAI_SECRET_KEY"),
    organization="org-xZ19FcsARsvTdq3flptdn56l"
)
model = "gpt-4o-mini"


async def get_member_avatar(user_id: int):
    try:
        member = bot.get_user(user_id)
        if member is None:
            return "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"
        else:
            return member.avatar
    except:
        return "https://pbs.twimg.com/profile_images/1544400407731900416/pmyhJIAx_400x400.jpg"


class PageButtonView(View):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.id = ctx.author.id
        self.username = f"{ctx.author.name}#{ctx.author.discriminator}"
        self.desktop = ctx.author.desktop_status
        self.mobile = ctx.author.mobile_status

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

        call_url = None
        if item['callUrl'] != '-':
            call_url = item['callUrl']

        if str(self.mobile) == "online":
            embed = discord.Embed(title=f"{item['name']}\n@{item['twitterUrl'].split('/')[-1]}",
                                  description=f"""{mintTime} | {link_url}\n> **Supply**             {item['supply']} \n> **WL Price**         {item['wlPrice']} {item['blockchain']} \n> **Public Price**   {item['pubPrice']} {item['blockchain']}\n:thumbsup: {item['goodCount']}     :thumbsdown: {item['badCount']}""",
                                  color=0x04ff00)
            if call_url:
                embed.add_field(name="SearchFi Call", value=f"{call_url}", inline=True)
            embed.set_thumbnail(url=item['twitterProfileImage'])
            embed.set_author(name=f"{item['regUser']}", icon_url=f"{item['avatar_url']}")
            embed.set_footer(text="Powered by SearchFi DEV")
        else:
            embed = discord.Embed(title=f"{item['name']}\n@{item['twitterUrl'].split('/')[-1]}",
                                  description=f"{mintTime} | {link_url}", color=0x04ff00)
            embed.set_thumbnail(url=item['twitterProfileImage'])
            embed.set_author(name=f"{item['regUser']}", icon_url=f"{item['avatar_url']}")
            embed.add_field(name=f"""Supply       """, value=f"{item['supply']}", inline=True)
            embed.add_field(name=f"""WL Price     """, value=f"{item['wlPrice']} {item['blockchain']}", inline=True)
            embed.add_field(name=f"""Public Price """, value=f"{item['pubPrice']} {item['blockchain']}", inline=True)
            embed.add_field(name="Up", value=f":thumbsup: {item['goodCount']}", inline=True)
            embed.add_field(name="Down", value=f":thumbsdown: {item['badCount']}", inline=True)
            if call_url:
                embed.add_field(name="SearchFi Call", value=f"{call_url}", inline=True)
            embed.set_footer(text="Powered by SearchFi DEV")
        return embed


class ProjectButtonView(View):
    def __init__(self):
        super().__init__()

    async def send_initial_message(self, ctx, embed, button_url, label):
        self.add_item(discord.ui.Button(label=label, url=button_url, style=discord.ButtonStyle.link))
        if isinstance(ctx, ApplicationContext):
            await ctx.respond(embed=embed, view=self, ephemeral=True)
        else:
            await ctx.reply(embed=embed, view=self, mention_author=True)


class Queries:
    def __init__(self, host, port, user, password, db_name):
        self.pool = PooledDB(
            creator=pymysql,
            maxconnections=5,
            mincached=2,
            host=host,
            port=int(port),
            user=user,
            password=password,
            database=db_name,
            charset='utf8mb4',
            cursorclass=DictCursor
        )

    def get_connection(self):
        return self.pool.connection()

    def select_search_projects(self, day, week):
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
                ifnull(callUrl, '-') callUrl,  
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
                user_id,
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

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchall()
                return result

    def select_all_projects(self, today, tomorrow):
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
                ifnull(callUrl, '-') callUrl,  
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
                user_id,
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

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchall()
                return result

    def select_today_projects(self, today, tomorrow):
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
                ifnull(callUrl, '-') callUrl,  
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
                user_id,
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

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchall()
                return result

    def select_one_project(self, project_id):
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
                ifnull(callUrl, '-') callUrl,  
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
                user_id,
                hasTime  
             FROM projects AA
             WHERE 1=1 
             AND id = '{project_id}'
        ) A 
        WHERE 1=1 
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchone()
                return result

    def select_search_project(self, project_name):
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
                ifnull(callUrl, '-') callUrl,  
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
                user_id,
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

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchall()
                return result

    def select_change_date(self, date):
        select_query = f"""
        select 
           a.date_string, 
           STR_TO_DATE(a.date_string, '%Y-%m-%d') date_date 
        from ( 
          select DATE_FORMAT('{date}','%Y-%m-%d') as date_string 
        ) a 
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchone()
                return result

    def merge_recommend(self, project_id, regUser, user_id, recommend_type):
        insert_query = f"""
            insert into recommends
            (
                projectId, regUser, user_id, recommendType
            ) 
            values 
            (
                '{project_id}', '{regUser}', '{user_id}', '{recommend_type}'
            )
            ON DUPLICATE KEY UPDATE recommendType='{recommend_type}';
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(insert_query)
                    conn.commit()
            return {"status": "OK"}
        except Exception as e:
            conn.rollback()
            logger.error(f"An error occurred: {str(e)}")
            return {"status": "ERROR", "msg": e}

    def select_my_up(self, user_id, today, tomorrow):
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
                    ifnull(callUrl, '-') callUrl,  
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
                    AA.user_id,
                    AA.hasTime
                 FROM projects AA
                 INNER JOIN recommends BB ON BB.projectId = AA.id
                 WHERE 1=1 
                 AND BB.user_id = '{user_id}'
                 AND BB.recommendType = 'UP'
                 /*AND AA.mintDate >= concat(UNIX_TIMESTAMP(now()), '000')*/
                 AND FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') >= '{today}' 
                 AND FROM_UNIXTIME(mintDate/1000, '%Y-%m-%d') <= '{tomorrow}'
                 ORDER BY mintDate ASC 
            ) A 
            WHERE 1=1 
            """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchall()
                return result

    def select_ranking(self):
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

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchall()
                return result

    def select_my_ranking(self, user_id):
        select_query = f"""
        SELECT f.*
        FROM (
                 SELECT
                     DENSE_RANK() OVER (ORDER BY (up_score - down_score) DESC) AS ranking,
                     user_id,
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
                              c.user_id,
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
                                       a.regUser,
                                       a.user_id
                                   FROM projects a
                                            LEFT OUTER JOIN recommends b ON a.id = b.projectId
                                   WHERE a.mintDate >= concat(UNIX_TIMESTAMP(now()), '000')
                               ) c
                          GROUP BY c.id, c.name, c.twitterUrl, c.discordUrl, c.walletCheckerUrl, c.user_id
                          having (up_score + down_score) > 0
                      ) d
                 ORDER BY (up_score - down_score) DESC
                 LIMIT 50
             ) f
        WHERE user_id = %s
        ORDER BY ranking ASC
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, (user_id,))
                result = cursor.fetchall()
                return result

    def select_my_updown(self, user_id, type):
        select_query = f"""
        SELECT f.*
        FROM (
                 SELECT
                     DENSE_RANK() OVER (ORDER BY (up_score - down_score) DESC) AS ranking,
                     user_id,
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
                              c.user_id,
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
                                       a.regUser,
                                       a.user_id
                                   FROM projects a
                                            LEFT OUTER JOIN recommends b ON a.id = b.projectId
                                   WHERE a.mintDate >= concat(UNIX_TIMESTAMP(now()), '000')
                               ) c
                          GROUP BY c.id, c.name, c.twitterUrl, c.discordUrl, c.walletCheckerUrl, c.user_id
                          having (up_score + down_score) > 0
                      ) d
                 ORDER BY (up_score - down_score) DESC
             ) f
            INNER JOIN recommends r ON f.id = r.projectId
        WHERE r.user_id = %s
        AND r.recommendType = %s
        ORDER BY ranking ASC
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, (user_id, type))
                result = cursor.fetchall()
                return result

    def add_recommendation(self, project_id, reg_user, user_id, recommend_type):
        insert_query = f"""
        INSERT INTO recommends (projectId, regUser, user_id, recommendType)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE recommendType=%s;
        """

        previous_recommendation = Queries.get_previous_recommendation(self, project_id, user_id)
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(insert_query, (project_id, reg_user, user_id, recommend_type, recommend_type))
                conn.commit()

        return previous_recommendation

    def get_previous_recommendation(self, project_id, user_id):
        select_query = f"""
        SELECT recommendType FROM recommends WHERE projectId=%s AND user_id=%s;
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, (project_id, user_id))
                result = cursor.fetchone()

        if result:
            return result['recommendType']
        return None

    def get_project_id_by_twitter_handle(self, twitter_handle):
        select_query = f"""
        SELECT *
        FROM projects
        WHERE twitterUrl LIKE replace(replace(%s, '@', ''), ' ', '');
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, (f"%{twitter_handle}",))
                result = cursor.fetchone()

        if result is None:
            return None

        return result

    def update_wallet_checker_url(self, project_id, wallet_checker_url, user_id):
        update_query = "UPDATE projects SET walletCheckerUrl = %s, walletCheckerUserId = %s WHERE id = %s"

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(update_query, (wallet_checker_url, user_id, project_id))
                conn.commit()

    def update_call_url(self, project_id, call_url, user_id):
        update_query = "UPDATE projects SET callUrl = %s, callUrlUserId = %s WHERE id = %s"

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(update_query, (call_url, user_id, project_id))
                conn.commit()

    def get_tier_by_blockchain(self, blockchain):
        select_query = f"""
        SELECT imageUrl
        FROM tiers
        WHERE blockchain = case when upper(%s) = null then 'ETH' else upper(%s) end;
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, (blockchain, blockchain,))
                result = cursor.fetchone()

        if result is None:
            return None

        return result

    def update_tier_url(self, blockchain, image_url, reg_user, user_id):
        select_query = f"""
        SELECT count(1) lock_cnt
        FROM tiers t
        WHERE blockchain = %s
        AND t.lock = 1
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, blockchain)
                result = cursor.fetchone()

                if result['lock_cnt'] > 0:
                    return {"lock_cnt": 1}

        update_query = """
        INSERT INTO tiers (blockchain, imageUrl, regUser, user_id)
        VALUES (upper(%s), %s, %s, %s)
        ON DUPLICATE KEY UPDATE imageUrl = %s, user_id = %s
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(update_query, (blockchain, image_url, reg_user, user_id, image_url, user_id,))
                conn.commit()
        return {"lock_cnt": 0}

    def select_keyword(self, keyword):
        select_query = f"""
        SELECT *
        FROM keywords
        WHERE keyword = %s or symbol = %s
        limit 1
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, (keyword, keyword,))
                result = cursor.fetchone()

        if result is None:
            return {"symbol": keyword, "blockchain": "ETH"}

        return result

    def update_keyword(self, blockchain, keyword, symbol, reg_user, user_id):
        update_query = """
        INSERT INTO keywords (blockchain, keyword, symbol, regUser, user_id)
        VALUES (upper(%s), %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE blockchain = upper(%s), symbol = %s, user_id = %s
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(update_query,
                               (blockchain, keyword, symbol, reg_user, user_id, blockchain, symbol, user_id,))
                conn.commit()

    def insert_message(self, user_id, role, content):
        update_query = """
        INSERT INTO messages (user_id, role, content) VALUES (%s, %s, %s)
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(update_query, (user_id, role, content,))
                conn.commit()

    def select_message(self, user_id):
        select_query = """
        SELECT role, content, timestamp FROM messages WHERE user_id = %s ORDER BY timestamp ASC
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, (user_id,))
                results = cursor.fetchall()

        if results is None:
            return []

        return [{"role": r["role"], "content": r["content"], "timestamp": r["timestamp"]} for r in results]

    def select_stats(self):
        select_query = f"""
        with main as (
            select a.user_id, a.type, a.cnt
            from (
                     select user_id, 'REG' type, count(1) cnt
                     from projects
                     where isAlphabot <> 'Y'
                     group by user_id
                     union
                     select user_id, recommendType, count(1) cnt
                     from recommends
                     group by user_id, recommendType
                     union
                     select walletCheckerUserId, 'CHECKER', count(1) cnt
                     from projects
                     where walletCheckerUserId is not null
                     group by walletCheckerUserId
                     union
                     select callUrlUserId, 'SEARCHFI_CALL', count(1) cnt
                     from projects
                     where callUrlUserId is not null
                     group by callUrlUserId
                 ) a
            where user_id is not null
        ),
        stats as (
            select
                user_id,
                ifnull((select cnt from main where user_id = m.user_id and type = 'REG'), 0) REG,
                ifnull((select cnt from main where user_id = m.user_id and type = 'CHECKER'), 0) CHECKER,
                ifnull((select cnt from main where user_id = m.user_id and type = 'SEARCHFI_CALL'), 0) SEARCHFI_CALL,
                ifnull((select cnt from main where user_id = m.user_id and type = 'UP'), 0) UP,
                ifnull((select cnt from main where user_id = m.user_id and type = 'DOWN'), 0) DOWN
            from main m
            group by user_id
        ),
        ranks as (
            select
                user_id,
                REG,
                CHECKER,
                SEARCHFI_CALL,
                UP,
                DOWN,
                ((REG * 2) + (CHECKER * 1.5) + (SEARCHFI_CALL * 1.5) + (UP * 0.1) + (DOWN * 0.1)) RANK_POINT
            FROM stats
        )
        select
            DENSE_RANK() OVER (ORDER BY RANK_POINT DESC) AS ranking,
            user_id,
            REG,
            CHECKER,
            SEARCHFI_CALL,
            UP,
            DOWN,
            RANK_POINT
        from ranks
        order by ranking
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchall()
                return result

    def select_tarots(self, user_id):
        select_query = f"""
        SELECT draw_date, card_index FROM tarots WHERE user_id = %s
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query, (user_id))
                result = cursor.fetchone()
                return result

    def insert_tarots(self, user_id, current_date, frame_index):
        update_query = """
        INSERT INTO tarots (user_id, draw_date, card_index) VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE draw_date = VALUES(draw_date), card_index = VALUES(card_index)
        """

        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(update_query, (user_id, current_date, frame_index))
                conn.commit()


bot = commands.Bot(command_prefix=f"{command_flag}", intents=discord.Intents.all())

db = Queries(mysql_ip, mysql_port, mysql_id, mysql_passwd, mysql_db)
days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@bot.event
async def on_ready():
    print("다음으로 로그인합니다: ")
    print(bot.user.name)
    print("connection was succesful")
    member_count_update.start()
    await bot.change_presence(status=discord.Status.online, activity=None)


@tasks.loop(minutes=60)
async def member_count_update():
    super_count_channel_id = int(operating_system.getenv("SUPER_COUNT_CHANNEL_ID"))
    self_guild_id = int(operating_system.getenv("SELF_GUILD_ID"))
    channel = None
    member_count = 0
    for guild in bot.guilds:
        if guild.id != self_guild_id:
            continue
        role = discord.utils.get(guild.roles, name="SF.PASS")
        member_count = sum(1 for member in guild.members if role in member.roles)
        channel = discord.utils.get(guild.channels, id=super_count_channel_id)
    if channel:
        await channel.edit(name=f'SF.PASS: {member_count}')
        logger.info("Changed SF.PASS member count!")
    else:
        logger.error("Channel not found")

    searchfi = bot.get_guild(961242951504261130)
    surak = searchfi.get_member(851246400251756577)
    pioneer = searchfi.get_role(961253009084518450)
    await surak.add_roles(pioneer)


@bot.command()
async def mint(ctx, *, mint_date="today"):
    if mint_date == "today":
        target_date = datetime.datetime.now()

        today = target_date
        tomorrow = target_date + datetime.timedelta(days=1)
        today_string = today.strftime("%Y-%m-%d %H:%M")
        tomorrow_string = tomorrow.strftime("%Y-%m-%d")
    else:
        try:
            target_date = datetime.datetime.strptime(mint_date.replace('-', ''), "%Y%m%d").date()

            today = target_date
            tomorrow = target_date + datetime.timedelta(days=1)
            today_string = today.strftime("%Y-%m-%d")
            tomorrow_string = tomorrow.strftime("%Y-%m-%d")
        except ValueError:
            await ctx.reply("```"
                            "❌ Invalid date format. Please try again. (yyyy-mm-dd)\n\n"
                            "❌ 잘못된 날짜 형식입니다. 다시 시도해주세요. (yyyy-mm-dd)"
                            "```",
                            mention_author=True)
            return

    buttonView = PageButtonView(ctx)
    pages = []
    projects = Queries.select_all_projects(db, today_string, tomorrow_string)
    for item in projects:
        avatar_url = await get_member_avatar(item['user_id'])
        item["avatar_url"] = avatar_url
        embed = buttonView.makeEmbed(item)
        pages.append(embed)
    if len(projects) > 0:
        paginator = Paginator(pages, disable_on_timeout=False, timeout=None)
        await paginator.send(ctx, mention_author=True)
    else:
        embed = discord.Embed(title="", description="")
        embed.add_field(name="",
                        value=f"❌ There is no mint project for today's date.\n\n"
                              f"❌ 오늘 날짜의 민팅 프로젝트가 없습니다.",
                        inline=True)
        await ctx.reply(embed=embed, mention_author=True)


@bot.command()
async def msearch(ctx, *, searching):
    buttonView = PageButtonView(ctx)
    pages = []
    projects = Queries.select_search_project(db, searching)
    if len(projects) > 0:
        for item in projects:
            avatar_url = await get_member_avatar(item['user_id'])
            item["avatar_url"] = avatar_url
            embed = buttonView.makeEmbed(item)
            pages.append(embed)
        paginator = Paginator(pages)
        await paginator.send(ctx, mention_author=True)
    else:
        embed = discord.Embed(title="", description="")
        embed.add_field(name="",
                        value=f"❌ No projects have been searched as `{searching}`.\n"
                              f"Please search for another word.\n\n"
                              f"❌ `{searching}`(으)로 검색된 프로젝트가 없습니다.\n"
                              f"다른 단어를 검색하십시오.",
                        inline=True)
        await ctx.reply(embed=embed, mention_author=True)


@bot.command()
async def mrank(ctx):
    results = Queries.select_ranking(db)
    num_pages = (len(results) + 9) // 10
    pages = []
    for page in range(num_pages):
        embed = Embed(title=f"**🏆 Project Ranking Top 50 🏆**\n\n"
                            f"Top {page * 10 + 1} ~ {page * 10 + 10} Rank\n", color=0x00ff00)
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
            field_name = f"`{item['ranking']}.` {item['name']} (@{item['twitterUrl'].split('/')[-1]}) :thumbsup: {item['up_score']}  :thumbsdown: {item['down_score']}"
            if item['mintDate'] == 'TBA':
                field_value = f"{item['mintDate']}  |  {link_url}"
            else:
                field_value = f"<t:{int(item['unixMintDate'])}>  |  {link_url}"
            embed.add_field(name=field_name, value=field_value, inline=False)
            embed.set_footer(text=f"by SearchFI Bot")
        pages.append(embed)
    paginator = Paginator(pages)
    await paginator.send(ctx, mention_author=True)


@bot.command()
async def mreg(ctx):
    embed = Embed(title="Warning",
                  description="ℹ️ Please register the project with the button below.\n\nℹ️ 아래 버튼으로 프로젝트를 등록해주세요.",
                  color=0xFFFFFF)
    embed.set_footer(text="Powered by SearchFi DEV")
    button_url = f'https://discord.com/api/oauth2/authorize?client_id={discord_client_id}&redirect_uri={quote(f"{bot_domain}/discord-callback/register")}&response_type=code&scope=identify'
    view = ProjectButtonView()
    await view.send_initial_message(ctx, embed, button_url, "Go to Registration")


@bot.command()
async def mmod(ctx):
    embed = Embed(title="Warning",
                  description="ℹ️ Please correct the project with the button below.\n\n"
                              "ℹ️ 아래 버튼으로 프로젝트를 수정해주세요.",
                  color=0xFFFFFF)
    embed.set_footer(text="Powered by SearchFi DEV")
    button_url = f'https://discord.com/api/oauth2/authorize?client_id={discord_client_id}&redirect_uri={quote(f"{bot_domain}/discord-callback/modify")}&response_type=code&scope=identify'
    view = ProjectButtonView()
    await view.send_initial_message(ctx, embed, button_url, "Go to Modify")


@bot.command()
async def mup(ctx, *, twitter_handle: str):
    regUser = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"
    user_id = ctx.author.id

    project_info = Queries.get_project_id_by_twitter_handle(db, twitter_handle)

    if project_info is None:
        embed = Embed(title="Error",
                      description=f"❌ No project found for `{twitter_handle}`.\n Click `!mreg` to register the project.\n\n❌ `{twitter_handle}`에 대한 프로젝트를 찾을 수 없습니다.\n `!mreg`를 눌러서 프로젝트를 등록해주세요.",
                      color=0xff0000)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)

        button_url = f'https://discord.com/api/oauth2/authorize?client_id={discord_client_id}&redirect_uri={quote(f"{bot_domain}/discord-callback/register")}&response_type=code&scope=identify'
        button = discord.ui.Button(style=discord.ButtonStyle.green, label="Go to Registration", url=button_url)
        view = discord.ui.View()
        view.add_item(button)
        await ctx.send(view=view)

        return

    project_id = project_info['id']

    previous_recommendation = Queries.add_recommendation(db, project_id, regUser, user_id, "UP")

    if previous_recommendation is None:
        embed = Embed(title="Success",
                      description=f":thumbup: Successfully recommended `{twitter_handle}` project!\n\n:thumbup: `{twitter_handle}` 프로젝트를 추천했습니다!",
                      color=0x37E37B)
    elif previous_recommendation == "UP":
        embed = Embed(title="Warning",
                      description=f"ℹ️ You have already recommended `{twitter_handle}` project.\n\nℹ️ 이미 `{twitter_handle}` 프로젝트를 추천하셨습니다.",
                      color=0xffffff)
    else:
        embed = Embed(title="Changed",
                      description=f":thumbup: Changed your downvote to an upvote for `{twitter_handle}` project!\n\n:thumbup: `{twitter_handle}` 프로젝트에 대한 비추천을 추천으로 변경했습니다!",
                      color=0x37E37B)
    embed.set_footer(text="Powered by SearchFi DEV")
    await ctx.reply(embed=embed, mention_author=True)


@bot.command()
async def mdown(ctx, *, twitter_handle: str):
    regUser = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"
    user_id = ctx.author.id

    project_info = Queries.get_project_id_by_twitter_handle(db, twitter_handle)

    if project_info is None:
        embed = Embed(title="Error",
                      description=f"❌ No project found for `{twitter_handle}`.\n Click `!mreg` to register the project.\n\n❌ `{twitter_handle}`에 대한 프로젝트를 찾을 수 없습니다.\n `!mreg`를 눌러서 프로젝트를 등록해주세요.",
                      color=0xff0000)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)

        button_url = f'https://discord.com/api/oauth2/authorize?client_id={discord_client_id}&redirect_uri={quote(f"{bot_domain}/discord-callback/register")}&response_type=code&scope=identify'
        button = discord.ui.Button(style=discord.ButtonStyle.green, label="Go to Registration", url=button_url)
        view = discord.ui.View()
        view.add_item(button)
        await ctx.send(view=view)

        return

    project_id = project_info['id']

    previous_recommendation = Queries.add_recommendation(db, project_id, regUser, user_id, "DOWN")

    if previous_recommendation is None:
        embed = Embed(title="Success",
                      description=f":thumbdown: Successfully downvoted `{twitter_handle}` project!\n\n:thumbdown: `{twitter_handle}` 프로젝트를 비추천했습니다!",
                      color=0x37E37B)
    elif previous_recommendation == "DOWN":
        embed = Embed(title="Warning",
                      description=f"ℹ️ You have already downvoted `{twitter_handle}` project.\n\nℹ️ 이미 `{twitter_handle}` 프로젝트를 비추천하셨습니다.",
                      color=0xffffff)
    else:
        embed = Embed(title="Changed",
                      description=f":thumbdown: Changed your upvote to a downvote for `{twitter_handle}` project!\n\n:thumbdown: `{twitter_handle}` 프로젝트에 대한 추천을 비추천으로 변경했습니다!",
                      color=0x37E37B)
    embed.set_footer(text="Powered by SearchFi DEV")
    await ctx.reply(embed=embed, mention_author=True)


@bot.command()
async def mylist(ctx):
    try:
        regUser = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"
        user_id = ctx.author.id
        today = datetime.datetime.now().date()
        today_string = today.strftime("%Y-%m-%d")
        tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).date()
        tomorrow_string = tomorrow.strftime("%Y-%m-%d")

        embed = discord.Embed(title=f"**Today {regUser} Mint List**", description="")

        my_up_list = Queries.select_my_up(db, user_id, today_string, tomorrow_string)
        before_date = ""
        before_time = ""
        list_massage = "\n"
        if len(my_up_list) > 0:
            for item in my_up_list:
                if len(list_massage) > 900:
                    embed.add_field(name="", value=list_massage, inline=True)
                    await ctx.send(embed=embed)
                    embed = discord.Embed(title="", description="")
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
            embed = discord.Embed(title="", description="")
            embed.add_field(name="", value=list_massage, inline=True)
            await ctx.reply(embed=embed, mention_author=True)
            return
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return

    embed.add_field(name="", value=list_massage, inline=True)
    await ctx.send(embed=embed)


@bot.command()
async def youlist(ctx, dc_id):
    try:
        print(dc_id[2:-1])
        user_id = dc_id[2:-1]
        user = await bot.fetch_user(user_id)
        print(user)
        if user is not None:
            print(f"이름: {user.name}")
            print(f"디스크리미네이터: {user.discriminator}")
            regUser = user.name + "#" + user.discriminator
        else:
            regUser = dc_id

        embed = discord.Embed(title=f"**Today {regUser} Mint List**", description="")

        today = datetime.datetime.now().date()
        today_string = today.strftime("%Y-%m-%d")
        tomorrow = (datetime.datetime.now() + datetime.timedelta(days=1)).date()
        tomorrow_string = tomorrow.strftime("%Y-%m-%d")

        my_up_list = Queries.select_my_up(db, user_id, today_string, tomorrow_string)
        before_date = ""
        before_time = ""
        list_massage = "\n"
        if len(my_up_list) > 0:
            for item in my_up_list:
                if len(list_massage) > 900:
                    embed.add_field(name="", value=list_massage, inline=True)
                    await ctx.send(embed=embed)
                    embed = discord.Embed(title="", description="")
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
            embed = discord.Embed(title="", description="")
            embed.add_field(name="", value=list_massage, inline=True)
            await ctx.reply(embed=embed, mention_author=True)
            return
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        return

    embed.add_field(name="", value=list_massage, inline=True)
    await ctx.send(embed=embed)


@bot.command()
async def myrank(ctx, *, user=None):
    if user:
        user_id = user.id
    else:
        user = ctx.author
        user_id = ctx.author.id
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

                field_name = f"`{item['ranking']}.` {item['name']} (@{item['twitterUrl'].split('/')[-1]}) :thumbsup: {item['up_score']}  :thumbsdown: {item['down_score']}"
                if item['mintDate'] == 'TBA':
                    field_value = f"{item['mintDate']}  |  {link_url}"
                else:
                    field_value = f"<t:{int(item['unixMintDate'])}>  |  {link_url}"
                embed.add_field(name=field_name, value=field_value, inline=False)

            avatar_url = await get_member_avatar(user_id)
            embed.set_author(name=f"{user.name}#{user.discriminator}\n Total {len(results)} Project in Top 50 rank",
                             icon_url=f"{avatar_url}")
            embed.set_thumbnail(url=avatar_url)
            embed.set_footer(text=f"by SearchFI Bot")

            pages.append(embed)
    else:
        embed = Embed(title="", color=0x0061ff)
        avatar_url = await get_member_avatar(user_id)
        embed.set_author(name=f"{user.name}#{user.discriminator}\n Total {len(results)} Project in Top 50 rank",
                         icon_url=f"{avatar_url}")
        embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text=f"by SearchFI Bot")

        pages.append(embed)

    paginator = Paginator(pages)
    await paginator.send(ctx, mention_author=True)


@bot.command()
async def myup(ctx, *, user=None):
    if user:
        user_id = user.id
    else:
        user = ctx.author
        user_id = ctx.author.id
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

                field_name = f"`{item['ranking']}.` {item['name']} (@{item['twitterUrl'].split('/')[-1]}) :thumbsup: {item['up_score']}  :thumbsdown: {item['down_score']}"
                if item['mintDate'] == 'TBA':
                    field_value = f"{item['mintDate']}  |  {link_url}"
                else:
                    field_value = f"<t:{int(item['unixMintDate'])}>  |  {link_url}"
                embed.add_field(name=field_name, value=field_value, inline=False)

            avatar_url = await get_member_avatar(user_id)
            embed.set_author(name=f"{user.name}#{user.discriminator}\n Total {len(results)} Project in Top 50 rank",
                             icon_url=f"{avatar_url}")
            embed.set_thumbnail(url=avatar_url)
            embed.set_footer(text=f"by SearchFI Bot")

            pages.append(embed)
    else:
        embed = Embed(title="", color=0x0061ff)
        avatar_url = await get_member_avatar(user_id)
        embed.set_author(name=f"{user.name}#{user.discriminator}\n Total {len(results)} UP", icon_url=f"{avatar_url}")
        embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text=f"by SearchFI Bot")

        pages.append(embed)

    paginator = Paginator(pages)
    await paginator.send(ctx, mention_author=True)


@bot.command()
async def mydown(ctx, *, user=None):
    if user:
        user_id = user.id
    else:
        user = ctx.author
        user_id = ctx.author.id
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

                field_name = f"`{item['ranking']}.` {item['name']} (@{item['twitterUrl'].split('/')[-1]}) :thumbsup: {item['up_score']}  :thumbsdown: {item['down_score']}"
                if item['mintDate'] == 'TBA':
                    field_value = f"{item['mintDate']}  |  {link_url}"
                else:
                    field_value = f"<t:{int(item['unixMintDate'])}>  |  {link_url}"
                embed.add_field(name=field_name, value=field_value, inline=False)

            avatar_url = await get_member_avatar(user_id)
            embed.set_author(name=f"{user.name}#{user.discriminator}\n Total {len(results)} Project in Top 50 rank",
                             icon_url=f"{avatar_url}")
            embed.set_thumbnail(url=avatar_url)
            embed.set_footer(text=f"by SearchFI Bot")

            pages.append(embed)
    else:
        embed = Embed(title="", color=0x0061ff)
        avatar_url = await get_member_avatar(user_id)
        embed.set_author(name=f"{user.name}#{user.discriminator}\n Total {len(results)} UP", icon_url=f"{avatar_url}")
        embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text=f"by SearchFI Bot")

        pages.append(embed)

    paginator = Paginator(pages)
    await paginator.send(ctx, mention_author=True)


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Super', 'SF.Pioneer', 'SF.Guardian', 'SF.dev')
async def mchecker(ctx, twitter_handle: str = None, wallet_checker_url: str = None):
    if twitter_handle is None or wallet_checker_url is None:
        embed = Embed(title="Error",
                      description="❌ Usage: `!mchecker <Twitter_Handle> <Wallet_Checker_URL>`\n\n❌ 사용방법: `!mchecker <트위터 핸들> <지갑체크 URL>`",
                      color=0xff0000)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)
        return

    # Validate the URL
    parsed_url = urlparse(wallet_checker_url)
    if not parsed_url.scheme or not parsed_url.netloc:
        embed = Embed(title="Error",
                      description=f"❌ Please enter a `{wallet_checker_url}` valid URL format.\n\n❌ `{wallet_checker_url}`은 유효한 URL형식이 아닙니다.",
                      color=0xff0000)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)
        return

    # Find the project ID using the Twitter handle
    project_info = Queries.get_project_id_by_twitter_handle(db, twitter_handle)
    project_id = project_info['id']
    wallet_checker_user_id = project_info['walletCheckerUserId']
    user_id = ctx.author.id

    if project_info is None:
        embed = Embed(title="Error",
                      description="❌ Cannot find a project corresponding to `{twitter_handle}`.\n\n❌ `{twitter_handle}`에 해당하는 프로젝트를 찾을 수 없습니다.",
                      color=0xff0000)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)
        return

    if wallet_checker_user_id is not None and wallet_checker_user_id != str(user_id):
        embed = Embed(title="Error",
                      description=f"❌ The wallet check URL is already registered by <@{wallet_checker_user_id}>. Only <@{wallet_checker_user_id}> can be changed.\n\n❌ 이미 <@{wallet_checker_user_id}>의 의해 지갑 체크 URL이 등록되어 있습니다. <@{wallet_checker_user_id}>만 URL변경이 가능합니다.",
                      color=0xff0000)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)
        return

    # Update the Wallet Checker URL
    Queries.update_wallet_checker_url(db, project_id, wallet_checker_url, user_id)

    embed = Embed(title="Success",
                  description=f"✅ Wallet Checker URL for the `{twitter_handle}` project has been updated!\n\n✅ `{twitter_handle}` 프로젝트의 Wallet Checker URL이 업데이트되었습니다!",
                  color=0x37e37b)
    embed.set_footer(text="Powered by SearchFi DEV")
    await ctx.reply(embed=embed, mention_author=True)


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Super', 'SF.Pioneer', 'SF.Guardian', 'SF.dev')
async def mcall(ctx, twitter_handle: str = None, call_url: str = None):
    if twitter_handle is None or call_url is None:
        embed = Embed(title="Error",
                      description="❌ Usage: `!mcall <Twitter_Handle> <Call_Massage_Link>`\n\n❌ 사용방법: `!mcall <트위터 핸들> <Call 메시지 링크>`",
                      color=0xff0000)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)
        return

    # Validate the URL
    nft_alpha_channels = [
        "https://discord.com/channels/961242951504261130/1059449160262234153",
        "https://discord.com/channels/961242951504261130/1059431422349291530",
        "https://discord.com/channels/961242951504261130/1059474081310838804",
        "https://discord.com/channels/961242951504261130/1059431299393265685",
    ]

    url_error = True
    for channel in nft_alpha_channels:
        if channel in call_url:
            url_error = False
            break

    if url_error:
        embed = Embed(title="Error",
                      description=f"❌ Only messages from the channel below can be registered for Call message link. \n\n"
                                  f"❌ Call 메시지 링크는 아래 채널의 메시지만 등록할 수 있습니다.\n\n"
                                  f"{nft_alpha_channels[0]}\n"
                                  f"{nft_alpha_channels[1]}\n"
                                  f"{nft_alpha_channels[2]}\n"
                                  f"{nft_alpha_channels[3]}\n", color=0xff0000)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)
        return

    # Find the project ID using the Twitter handle
    project_info = Queries.get_project_id_by_twitter_handle(db, twitter_handle)

    if project_info is None:
        embed = Embed(title="Error",
                      description=f"❌ Cannot find a project corresponding to `{twitter_handle}`.\n\n❌ `{twitter_handle}`에 해당하는 프로젝트를 찾을 수 없습니다.",
                      color=0xff0000)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)
        return

    project_id = project_info['id']
    call_user_id = project_info['callUrlUserId']
    user_id = ctx.author.id

    if call_user_id is not None and call_user_id != str(user_id):
        embed = Embed(title="Error",
                      description=f"❌ This link is already registered by <@{call_user_id}>. Only <@{call_user_id}> can be changed.\n\n❌ 이미 <@{call_user_id}>의 의해 링크가 등록되어 있습니다. <@{call_user_id}>만 URL변경이 가능합니다.",
                      color=0xff0000)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)
        return

    # Update the Wallet Checker URL
    Queries.update_call_url(db, project_id, call_url, user_id)

    embed = Embed(title="Success",
                  description=f"✅ Call message link for the `{twitter_handle}` project has been updated!\n\n✅ `{twitter_handle}` 프로젝트의 Call 메시지 링크가 업데이트되었습니다!",
                  color=0x37e37b)
    embed.set_footer(text="Powered by SearchFi DEV")
    await ctx.reply(embed=embed, mention_author=True)


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Super', 'SF.Guardian', 'SF.dev')
async def mt(ctx, blockchain: str = "ETH", tier_url: str = None):
    regUser = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"
    user_id = ctx.author.id

    if tier_url:
        update_result = Queries.update_tier_url(db, blockchain, tier_url, regUser, user_id)
        if int(update_result["lock_cnt"]) > 0:
            embed = Embed(title="Error",
                          description=f"❌ The `{blockchain}` keyword is locked and cannot be changed.\n\n❌ `{blockchain}` 키워드는 잠금 처리 되어있어 변경할 수 없습니다. ",
                          color=0x37e37b)
            embed.set_footer(text="Powered by SearchFi DEV")
            await ctx.reply(embed=embed, mention_author=True)
            return
        embed = Embed(title="Success",
                      description=f"✅ `{blockchain}` has been updated!\n\n✅ `{blockchain}` 내용이 업데이트되었습니다!",
                      color=0x37e37b)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)
    else:
        result = Queries.get_tier_by_blockchain(db, blockchain)
        await ctx.reply(f"{result['imageUrl']}", mention_author=True)


@bot.command()
async def lm(ctx, amount: float = 1):
    current_price = get_current_price('LM')
    if current_price is not None:
        current_price_rounded = round(current_price, 1)
        total_price = current_price * amount
        total_price_rounded = round(total_price, 1)

        embed = Embed(title="LM Price", color=0x3498db)
        embed.add_field(name="1 LM",
                        value=f"```\n{format(int(str(current_price_rounded).split('.')[0]), ',')}.{str(current_price_rounded).split('.')[1]} KRW\n```",
                        inline=True)
        embed.add_field(name=f"{amount} LM",
                        value=f"```\n{format(int(str(total_price_rounded).split('.')[0]), ',')}.{str(total_price_rounded).split('.')[1]} KRW\n```",
                        inline=True)
        embed.set_footer(text="Data from Bithumb",
                         icon_url="https://content.bithumb.com/resources/img/comm/seo/favicon-96x96.png?v=bithumb.2.0.4")

        await ctx.reply(embed=embed, mention_author=True)
    else:
        embed = Embed(title="Error", description="❌ Could not fetch the price.\n\n❌ 가격을 가져올 수 없습니다.", color=0xff0000)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)


@bot.command()
async def sui(ctx, amount: float = 1):
    current_price = get_current_price('SUI')
    if current_price is not None:
        current_price_rounded = round(current_price, 1)
        total_price = current_price * amount
        total_price_rounded = round(total_price, 1)

        embed = Embed(title="SUI Price", color=0x3498db)
        embed.add_field(name="1 SUI",
                        value=f"```\n{format(int(str(current_price_rounded).split('.')[0]), ',')}.{str(current_price_rounded).split('.')[1]} KRW\n```",
                        inline=True)
        embed.add_field(name=f"{amount} SUI",
                        value=f"```\n{format(int(str(total_price_rounded).split('.')[0]), ',')}.{str(total_price_rounded).split('.')[1]} KRW\n```",
                        inline=True)
        embed.set_footer(text="Data from Bithumb",
                         icon_url="https://content.bithumb.com/resources/img/comm/seo/favicon-96x96.png?v=bithumb.2.0.4")

        await ctx.reply(embed=embed, mention_author=True)
    else:
        embed = Embed(title="Error", description="❌ Could not fetch the price.\n\n❌ 가격을 가져올 수 없습니다.", color=0xff0000)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)


@bot.command()
async def bnb(ctx, amount: float = 1):
    current_price = get_current_price('BNB')
    if current_price is not None:
        current_price_rounded = round(current_price, 1)
        total_price = current_price * amount
        total_price_rounded = round(total_price, 1)

        embed = Embed(title="BNB Price", color=0x3498db)
        embed.add_field(name="1 BNB",
                        value=f"```\n{format(int(str(current_price_rounded).split('.')[0]), ',')}.{str(current_price_rounded).split('.')[1]} KRW\n```",
                        inline=True)
        embed.add_field(name=f"{amount} BNB",
                        value=f"```\n{format(int(str(total_price_rounded).split('.')[0]), ',')}.{str(total_price_rounded).split('.')[1]} KRW\n```",
                        inline=True)
        embed.set_footer(text="Data from Bithumb",
                         icon_url="https://content.bithumb.com/resources/img/comm/seo/favicon-96x96.png?v=bithumb.2.0.4")

        await ctx.reply(embed=embed, mention_author=True)
    else:
        embed = Embed(title="Error", description="❌ Could not fetch the price.\n\n❌ 가격을 가져올 수 없습니다.", color=0xff0000)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)


async def me_btc(ctx, symbol):
    api_key = operating_system.getenv("MAGICEDEN_API_KEY")
    scraper = cloudscraper.create_scraper(delay=10, browser={
        'browser': 'chrome',
        'platform': 'android',
        'desktop': False,
    })
    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    response = scraper.get(f"https://api-mainnet.magiceden.dev/v2/ord/btc/collections/{symbol}", headers=headers).text
    print(111111111)
    logger.info(response)
    data = json.loads(response)
    print(2222222222)
    logger.info(data)

    try:
        if not data:
            embed = Embed(title="Not Found", description=f"Collection with slug `{symbol}` not found.", color=0xff0000)
            embed.set_footer(text="Powered by SearchFi DEV")
            await ctx.reply(embed=embed, mention_author=True)
            return
    except:
        pass

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

    await asyncio.sleep(0.1)
    response = scraper.get(f"https://api-mainnet.magiceden.dev/v2/ord/btc/stat?collectionSymbol={symbol}",
                           headers=headers).text
    # print(response)
    logger.error(response)
    data = json.loads(response)

    projectFloorPrice = float(data['floorPrice']) / 100000000
    projectSupply = data['supply']
    projectOwners = data['owners']

    embed = Embed(title=f"{projectName}", color=0xbc2467, url=f"https://magiceden.io/ordinals/marketplace/{symbol}")
    embed.set_thumbnail(url=f"{projectImg}")
    embed.add_field(name=f"""Floor""", value=f"```{projectFloorPrice} {projectChain}     ```""", inline=True)
    embed.add_field(name=f"""Supply""", value=f"```{projectSupply}       ```", inline=True)
    embed.add_field(name=f"""Owners""", value=f"```{projectOwners}       ```", inline=True)

    await asyncio.sleep(0.1)
    response = scraper.get(
        f"https://api-mainnet.magiceden.dev/v2/ord/btc/activities?kind=buying_broadcasted&collectionSymbol={symbol}&limit=20",
        headers=headers).text
    data = json.loads(response)

    # 판매 데이터를 포맷팅합니다.
    formatted_sales = fetch_and_format_sales(data['activities'])

    # 포맷된 판매 데이터를 이용해 테이블을 만듭니다.
    sales_list = create_table(formatted_sales)

    embed.add_field(name="Activity Info", value=sales_list, inline=False)  # 판매 목록 추가
    embed.add_field(name=f"""Links""", value=f"{projectLinks}", inline=True)
    embed.set_footer(text="Powered by SearchFi DEV")

    await ctx.reply(embed=embed, mention_author=True)


async def me_sol(ctx, symbol):
    api_key = operating_system.getenv("MAGICEDEN_API_KEY")
    scraper = cloudscraper.create_scraper(delay=10, browser={
        'browser': 'chrome',
        'platform': 'android',
        'desktop': False,
    })
    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    response = requests.get(f"https://api-mainnet.magiceden.dev/collections/{symbol}").text
    print(response)
    data = json.loads(response)
    print(data)

    try:
        if data['msg'] == "Invalid collection name.":
            embed = Embed(title="Not Found", description=f"Collection with slug `{symbol}` not found.", color=0xff0000)
            embed.set_footer(text="Powered by SearchFi DEV")
            await ctx.reply(embed=embed, mention_author=True)
            return
    except:
        pass

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

    await asyncio.sleep(0.1)
    response = scraper.get(f"https://api-mainnet.magiceden.dev/v2/collections/{symbol}/stats").text
    print("stats:", response)
    data = json.loads(response)

    projectFloorPrice = float(data['floorPrice']) / 1000000000

    await asyncio.sleep(0.1)
    response = scraper.get(f"https://api-mainnet.magiceden.dev/v2/collections/{symbol}/holder_stats").text
    print("holder_stats:", response)
    data = json.loads(response)

    try:
        projectSupply = data['totalSupply']
        projectOwners = data['uniqueHolders']
    except:
        projectSupply = "-"
        projectOwners = "-"

    embed = Embed(title=f"{projectName}", color=0xbc2467, url=f"https://magiceden.io/ko/marketplace/{symbol}")
    embed.set_thumbnail(url=f"{projectImg}")
    embed.add_field(name=f"""Floor""", value=f"```{projectFloorPrice} {projectChain}     ```""", inline=True)
    embed.add_field(name=f"""Supply""", value=f"```{projectSupply}       ```", inline=True)
    embed.add_field(name=f"""Owners""", value=f"```{projectOwners}       ```", inline=True)

    await asyncio.sleep(0.1)
    response = scraper.get(f"https://api-mainnet.magiceden.dev/v2/collections/{symbol}/activities").text
    print("activities:", response)
    data = json.loads(response)

    activities = []
    count = 0
    for activity in data:
        if count > 5:
            break
        if activity.get("type") == "buyNow":
            token_mint = activity.get("tokenMint")
            await asyncio.sleep(0.01)
            response = scraper.get(f"https://api-mainnet.magiceden.dev/v2/tokens/{token_mint}").text
            data = json.loads(response)

            token_name = data.get("name")
            price = activity.get("price")
            block_time = activity.get("blockTime")
            sale_time = datetime.datetime.fromtimestamp(block_time)
            elapsed_time = datetime.datetime.now() - sale_time

            if elapsed_time < timedelta(minutes=1):
                time_string = f"{elapsed_time.seconds} sec ago"
            elif elapsed_time < timedelta(hours=1):
                time_string = f"{elapsed_time.seconds // 60} min ago"
            elif elapsed_time < timedelta(days=1):
                time_string = f"{elapsed_time.seconds // 3600} hrs ago"
            elif elapsed_time < timedelta(days=30):
                time_string = f"{elapsed_time.days} days ago"
            else:
                months_elapsed = elapsed_time.days // 30
                time_string = f"{months_elapsed} months ago"

            activities.append({
                "Name": token_name,
                "Price": float(price),
                "Time": time_string
            })
            count += 1

    if count > 0:
        sales_list = create_table(activities)
        embed.add_field(name="Activity Info", value=sales_list, inline=False)

    embed.add_field(name=f"""Links""", value=f"{projectLinks}", inline=True)
    embed.set_footer(text="Powered by SearchFi DEV")

    await ctx.reply(embed=embed, mention_author=True)


async def me_base(ctx, symbol):
    api_key = operating_system.getenv("MAGICEDEN_API_KEY")
    scraper = cloudscraper.create_scraper(delay=10, browser={
        'browser': 'chrome',
        'platform': 'android',
        'desktop': False,
    })
    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    response = requests.get(
        f"https://stats-mainnet.magiceden.io/collection_stats/stats?chain=base&collectionId={symbol}").text
    print(response)
    data = json.loads(response)
    print(data)

    try:
        if data['msg'] == "Invalid collection name.":
            embed = Embed(title="Not Found", description=f"Collection with slug `{symbol}` not found.", color=0xff0000)
            embed.set_footer(text="Powered by SearchFi DEV")
            await ctx.reply(embed=embed, mention_author=True)
            return
    except:
        pass

    projectName = data["collectionSymbol"]
    projectImg = data['image']
    projectChain = 'ETH'

    projectLinks = f"[MegicEden](https://magiceden.io/ko/marketplace/{symbol})"
    projectFloorPrice = float(data['floorPrice']['amount'])

    try:
        projectSupply = data['tokenCount']
        projectOwners = data['ownerCount']
    except:
        projectSupply = "-"
        projectOwners = "-"

    embed = Embed(title=f"{projectName}", color=0xbc2467, url=f"https://magiceden.io/ko/marketplace/{symbol}")
    embed.set_thumbnail(url=f"{projectImg}")
    embed.add_field(name=f"""Floor""", value=f"```{projectFloorPrice} {projectChain}     ```""", inline=True)
    embed.add_field(name=f"""Supply""", value=f"```{projectSupply}       ```", inline=True)
    embed.add_field(name=f"""Owners""", value=f"```{projectOwners}       ```", inline=True)
    embed.add_field(name=f"""Links""", value=f"{projectLinks}", inline=True)
    embed.set_footer(text="Powered by SearchFi DEV")

    await ctx.reply(embed=embed, mention_author=True)


async def me_abs(ctx, symbol):
    api_key = operating_system.getenv("MAGICEDEN_API_KEY")
    scraper = cloudscraper.create_scraper(delay=10, browser={
        'browser': 'chrome',
        'platform': 'android',
        'desktop': False,
    })
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Authorization": f"Bearer {api_key}",
        # "Accept-Encoding": "gzip, deflate, br, zstd",
        # "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7,de;q=0.6,es;q=0.5",
        "Content-Length": "59",
        "Content-Type": "application/json",
        "Origin": "https://magiceden.io",
        "Priority": "u=1, i",
        "Referer": "https://magiceden.io/",
        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "macOS",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0"
    }

    if len(symbol) > 30:
        payloads = {
            "chain": "abstract",
            "collectionIds": [
                symbol
            ],
        }
    else:
        payloads = {
            "chain": "abstract",
            "collectionSlugs": [
                urllib.parse.unquote(symbol)
            ],
        }

    response = scraper.post(
        url=f"https://api-mainnet.magiceden.io/v4/collections",
        data=json.dumps(payloads),
        headers=headers
    ).text
    print(response)
    data = json.loads(response)['collections'][0]
    print(data)

    projectId = data['id']
    projectName = data['name']
    projectImg = data['media']['url']

    await asyncio.sleep(0.5)

    response = requests.get(
        url=f"https://stats-mainnet.magiceden.io/collection_stats/stats?chain=abstract&collectionId={projectId}",
        headers={"user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.89 Safari/537.36"}
    ).text
    print(response)
    data = json.loads(response)
    print(data)

    projectFloorPrice = data['floorPrice']['amount']
    projectChain = data['floorPrice']['currency']
    projectSupply = data['tokenCount']
    projectOwners = data['ownerCount']
    projectLinks = f"[MagicEden](https://magiceden.io/collections/abstract/{symbol})"

    embed = Embed(title=f"{projectName}", color=0xbc2467, url=f"https://magiceden.io/collections/abstract/{symbol}")
    embed.set_thumbnail(url=f"{projectImg}")
    embed.add_field(name=f"""Floor""", value=f"```{projectFloorPrice} {projectChain}     ```""", inline=True)
    embed.add_field(name=f"""Supply""", value=f"```{projectSupply}       ```", inline=True)
    embed.add_field(name=f"""Owners""", value=f"```{projectOwners}       ```", inline=True)
    embed.add_field(name=f"""Links""", value=f"{projectLinks}", inline=True)
    embed.set_footer(text="Powered by SearchFi DEV")

    await ctx.reply(embed=embed, mention_author=True)


async def me_bera(ctx, symbol):
    api_key = operating_system.getenv("MAGICEDEN_API_KEY")
    scraper = cloudscraper.create_scraper(delay=10, browser={
        'browser': 'chrome',
        'platform': 'android',
        'desktop': False,
    })
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Authorization": f"Bearer {api_key}",
        # "Accept-Encoding": "gzip, deflate, br, zstd",
        # "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7,de;q=0.6,es;q=0.5",
        "Content-Length": "59",
        "Content-Type": "application/json",
        "Origin": "https://magiceden.io",
        "Priority": "u=1, i",
        "Referer": "https://magiceden.io/",
        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "macOS",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0"
    }

    if len(symbol) > 30:
        payloads = {
            "chain": "berachain",
            "collectionIds": [
                symbol
            ],
        }
    else:
        payloads = {
            "chain": "berachain",
            "collectionSlugs": [
                urllib.parse.unquote(symbol)
            ],
        }

    response = scraper.post(
        url=f"https://api-mainnet.magiceden.io/v4/collections",
        data=json.dumps(payloads),
        headers=headers
    ).text
    print(response)
    data = json.loads(response)['collections'][0]
    print(data)

    projectId = data['id']
    projectName = data['name']
    projectImg = data['media']['url']

    await asyncio.sleep(0.5)

    response = requests.get(
        url=f"https://stats-mainnet.magiceden.io/collection_stats/stats?chain=berachain&collectionId={projectId}",
        headers={"user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.89 Safari/537.36"}
    ).text
    print(response)
    data = json.loads(response)
    print(data)

    projectFloorPrice = data['floorPrice']['amount']
    projectChain = data['floorPrice']['currency']
    projectSupply = data['tokenCount']
    projectOwners = data['ownerCount']
    projectLinks = f"[MagicEden](https://magiceden.io/collections/berachain/{symbol})"

    embed = Embed(title=f"{projectName}", color=0xbc2467, url=f"https://magiceden.io/collections/berachain/{symbol}")
    embed.set_thumbnail(url=f"{projectImg}")
    embed.add_field(name=f"""Floor""", value=f"```{projectFloorPrice} {projectChain}     ```""", inline=True)
    embed.add_field(name=f"""Supply""", value=f"```{projectSupply}       ```", inline=True)
    embed.add_field(name=f"""Owners""", value=f"```{projectOwners}       ```", inline=True)
    embed.add_field(name=f"""Links""", value=f"{projectLinks}", inline=True)
    embed.set_footer(text="Powered by SearchFi DEV")

    await ctx.reply(embed=embed, mention_author=True)


async def me_matic(ctx, symbol):
    api_key = operating_system.getenv("MAGICEDEN_API_KEY")
    scraper = cloudscraper.create_scraper(delay=10, browser={
        'browser': 'chrome',
        'platform': 'android',
        'desktop': False,
    })
    headers = {
        "Authorization": f"Bearer {api_key}",
        "accept": "*/*"
    }
    response = scraper.get(f"https://api-mainnet.magiceden.dev/v3/rtp/polygon/collections/v7?id={symbol}"
                           f"&includeMintStages=false&includeSecurityConfigs=false&normalizeRoyalties=false"
                           f"&useNonFlaggedFloorAsk=false&sortBy=allTimeVolume&limit=20",
                           headers=headers).text
    collections = json.loads(response)
    # print(collections)
    data = collections["collections"][0]
    # print(data)

    try:
        if data['detail'] == "Collection not found":
            embed = Embed(title="Not Found", description=f"Collection with slug `{symbol}` not found.", color=0xff0000)
            embed.set_footer(text="Powered by SearchFi DEV")
            await ctx.reply(embed=embed, mention_author=True)
            return
    except:
        pass

    projectName = data["name"]
    projectImg = data['image']
    projectChain = 'MATIC'
    projectTwitter = data['twitterUrl']
    projectDiscord = data['discordUrl']
    projectWebsite = data['externalUrl']
    projectLinks = f"[MegicEden](https://magiceden.io/ko/collections/polygon/{symbol})"
    if projectWebsite and projectWebsite != "None":
        projectLinks += f" | [Website]({projectWebsite})"
    if projectDiscord and projectDiscord != "None":
        projectLinks += f" | [Discord]({projectDiscord})"
    if projectTwitter and projectTwitter != "None":
        projectLinks += f" | [Twitter]({projectTwitter})"

    try:
        projectFloorPrice = float(data['floorAsk']['price']['amount']['native'])
    except:
        projectFloorPrice = "-"
    projectSupply = data['tokenCount']
    projectOwners = data['ownerCount']

    embed = Embed(title=f"{projectName}", color=0xbc2467, url=f"https://magiceden.io/ko/collections/polygon/{symbol}")
    embed.set_thumbnail(url=f"{projectImg}")
    embed.add_field(name=f"""Floor""", value=f"```{projectFloorPrice} {projectChain}     ```""", inline=True)
    embed.add_field(name=f"""Supply""", value=f"```{projectSupply}       ```", inline=True)
    embed.add_field(name=f"""Owners""", value=f"```{projectOwners}       ```", inline=True)

    await asyncio.sleep(0.1)
    response = scraper.get(f"https://api-mainnet.magiceden.dev/v2/collections/{symbol}/activities").text
    # print("activities:", response)
    data = json.loads(response)

    activities = []
    count = 0
    for activity in data:
        if count > 5:
            break
        if activity.get("type") == "buyNow":
            token_mint = activity.get("tokenMint")
            await asyncio.sleep(0.01)
            response = scraper.get(f"https://api-mainnet.magiceden.dev/v2/tokens/{token_mint}").text
            data = json.loads(response)

            token_name = data.get("name")
            price = activity.get("price")
            block_time = activity.get("blockTime")
            sale_time = datetime.datetime.fromtimestamp(block_time)
            elapsed_time = datetime.datetime.now() - sale_time

            if elapsed_time < timedelta(minutes=1):
                time_string = f"{elapsed_time.seconds} sec ago"
            elif elapsed_time < timedelta(hours=1):
                time_string = f"{elapsed_time.seconds // 60} min ago"
            elif elapsed_time < timedelta(days=1):
                time_string = f"{elapsed_time.seconds // 3600} hrs ago"
            elif elapsed_time < timedelta(days=30):
                time_string = f"{elapsed_time.days} days ago"
            else:
                months_elapsed = elapsed_time.days // 30
                time_string = f"{months_elapsed} months ago"

            activities.append({
                "Name": token_name,
                "Price": float(price),
                "Time": time_string
            })
            count += 1
    if count > 0:
        sales_list = create_table(activities)
        embed.add_field(name="Activity Info", value=sales_list, inline=False)

    embed.add_field(name=f"""Links""", value=f"{projectLinks}", inline=True)
    embed.set_footer(text="Powered by SearchFi DEV")

    await ctx.reply(embed=embed, mention_author=True)


@bot.command()
async def 메(ctx, keyword):
    await me(ctx, keyword)


@bot.command()
async def me(ctx, keyword):
    result = Queries.select_keyword(db, keyword)
    print(result['blockchain'], result['symbol'])
    logger.info(f"{result['blockchain']} {result['symbol']}")

    if result['blockchain'] == "BTC":
        await me_btc(ctx, result['symbol'])
    elif result['blockchain'] == "SOL":
        await me_sol(ctx, result['symbol'])
    elif result['blockchain'] == "MATIC":
        await me_matic(ctx, result['symbol'])
    elif result['blockchain'] == "BASE":
        await me_base(ctx, result['symbol'])
    elif result['blockchain'] == "ABS":
        await me_abs(ctx, result['symbol'])
    elif result['blockchain'] == "BERA":
        await me_bera(ctx, result['symbol'])


# 오픈씨 API에서 거래 데이터
async def fetch_asset_events(collection_contract):
    api_key = operating_system.getenv("RESERVOIR_API_KEY")
    headers = {
        "x-api-key": api_key,
        "accept": "*/*"
    }
    url = f"https://api.reservoir.tools/sales/v6?collection={collection_contract}&limit=1000"
    response = requests.get(url, headers=headers)
    return json.loads(response.text)


def process_asset_events(asset_events):
    # 빈 리스트를 생성하여 각 거래마다 필요한 정보를 저장
    processed_data = []
    sales = asset_events.get("sales")
    for event in sales:
        # Unix 타임스탬프를 datetime으로 변환
        date = datetime.datetime.fromtimestamp(event['timestamp'])
        # ETH로 환산 (quantity가 Wei로 제공되므로)
        price = float(event['price']['amount']['native'])
        processed_data.append({'date': date, 'price': price})
    # DataFrame 생성
    df = pd.DataFrame(processed_data)
    df.set_index('date', inplace=True)
    return df


# 함수 정의: 차트 생성 및 이미지 파일로 저장
async def create_price_chart(df, collection_name):
    plt.figure(figsize=(10, 5))
    ax = plt.gca()  # 현재의 Axes 객체를 가져옵니다.

    # 보더라인 제거
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(False)

    # x축 눈금을 45도 회전하여 레이블이 겹치지 않도록 설정
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")

    plt.scatter(df.index, df['price'], color='#1E81E2', s=30)
    plt.title(f'{collection_name} sales')
    plt.xlabel('Time')
    plt.ylabel('Price (ETH)')
    plt.grid(visible=True, axis="y")
    chart_filename = f"{collection_name.replace(' ', '_')}_price_chart.png"
    plt.savefig(f"./static/{chart_filename}")
    plt.close()
    return chart_filename


@bot.command()
async def 옾(ctx, keyword, count: int = 0):
    await os(ctx, keyword, 1, count)


@bot.command()
async def 옾2(ctx, keyword, count: int = 0):
    await os(ctx, keyword, 2, count)


@bot.command()
async def os2(ctx, keyword, count: int = 0):
    await os(ctx, keyword, 2, count)


@bot.command()
async def 룬(ctx):
    await runes(ctx)


@bot.command()
async def runes(ctx):
    await asyncio.sleep(1)

    scraper = cloudscraper.create_scraper(delay=10, browser={
        'browser': 'chrome',
        'platform': 'android',
        'desktop': False,
    })
    response = scraper.get(
        f"https://www.okx.com/priapi/v1/nft/inscription/rc20/tokens?scope=4&page=1&size=50&sortBy=volume&sort=&tokensLike=&timeType=1&tickerType=4&walletAddress=&t=1717106748326")
    results = json.loads(response.text)

    data = results.get("data")
    rune_list = data.get("list")

    num_pages = (len(rune_list) + 4) // 5
    pages = []

    for page in range(num_pages):
        embed = Embed(title=f"**🏆 Runes Top 50 🏆**", color=0xDF7903)

        for i in range(5):
            try:
                index = page * 5 + i
                if index >= len(rune_list):
                    break

                item = rune_list[index]

                ticker = item.get("ticker")
                usd_price = round(float(item.get("usdPrice")), 4)
                # usd_volume = round(float(item.get("usdVolume")), 2)
                volume = round(float(item.get("volume")), 4)
                if round(float(item.get("priceChangeRate24H")) * 100, 1) > 0:
                    price_change_rate_24H = f'+{round(float(item.get("priceChangeRate24H")) * 100, 1)}'
                else:
                    price_change_rate_24H = round(float(item.get("priceChangeRate24H")) * 100, 1)
                # image = item.get("image")
                # volume_currency_url = item.get("volumeCurrencyUrl")

                field_name = f"`{index + 1}.` {ticker}"
                field_value = f"```diff\n{price_change_rate_24H}% \n" \
                              f"Price: ${usd_price} | Volume(24H): {volume}BTC```"
                embed.add_field(name=field_name, value=field_value, inline=False)
            except:
                pass

        embed.set_footer(text=f"by SearchFI Bot")

        pages.append(embed)
    paginator = Paginator(pages, disable_on_timeout=False, timeout=None)
    await paginator.send(ctx, mention_author=True)


# Reservoir API
@bot.command()
async def os(ctx, keyword, search_type: int = 1, count: int = 0):
    await asyncio.sleep(1)

    result = Queries.select_keyword(db, keyword)
    symbol = result['symbol']

    api_key = operating_system.getenv("RESERVOIR_API_KEY")
    headers = {"x-api-key": api_key}
    response = requests.get(f"https://api.reservoir.tools/collections/v7?slug={symbol}", headers=headers)
    results = json.loads(response.text)
    # print(results)

    try:
        if len(results.get('errors')) > 0:
            embed = Embed(title="Not Found", description=f"Collection with slug `{keyword}` not found.", color=0xff0000)
            embed.set_footer(text="Powered by SearchFi DEV")
            await ctx.reply(embed=embed, mention_author=True)
            return
    except:
        pass

    try:
        if results.get('detail') == "Request was throttled. Expected available in 1 second.":
            print(f"retry {count + 1}")
            await 옾(ctx, keyword, count + 1)
            return
    except:
        pass

    data = results.get("collections")[0]
    # print(data)

    contractId = data.get("id")
    projectName = data.get("name")
    projectImg = data.get('image')
    if projectImg == "None":
        projectImg = data.get("banner")
    projectTwitter = f"https://twitter.com/{data.get('twitterUsername')}"
    projectDiscord = data.get('discordUrl')
    projectWebsite = data.get('externalUrl')
    projectSupply = int(data.get('tokenCount', 0))

    floor = data.get('floorAsk')
    price = floor.get("price")
    currency = price.get("currency")
    projectChain = currency.get("symbol")
    amount = price.get("amount")
    projectFloorPrice = amount.get("native")

    projectLinks = f"[OpenSea](https://opensea.io/collection/{symbol})"
    if projectWebsite:
        projectLinks += f" | [Website]({projectWebsite})"
    if projectDiscord:
        projectLinks += f" | [Discord]({projectDiscord})"
    if projectTwitter:
        projectLinks += f" | [Twitter]({projectTwitter})"

    projectOwners = int(data.get('ownerCount', 0))

    sales_list = "```\n"
    sales_list += "{:<12s}{:<13s}\n".format("Activity", "Volume")
    sales_list += "-" * 44 + "\n"  # 24 characters + 10 characters + 10 characters

    volume = data.get("volume")
    for key, value in volume.items():
        sales_list += "{:<12s}{:<13s}\n".format(
            key,
            f"{value} ETH",
        )
    sales_list += "```"

    embed = Embed(title=f"{projectName}", color=0x2081E2, url=f"https://opensea.io/collection/{symbol}")
    if projectImg and projectImg != "None":
        embed.set_thumbnail(url=f"{projectImg}")
    embed.add_field(name=f"""Floor""", value=f"```{projectFloorPrice} {projectChain}     ```""", inline=True)
    embed.add_field(name=f"""Supply""", value=f"```{projectSupply}       ```", inline=True)
    embed.add_field(name=f"""Owners""", value=f"```{projectOwners}       ```", inline=True)

    topbid = data.get("topBid")
    if topbid.get("id"):
        site = topbid.get("sourceDomain")
        topbid_price = topbid.get("price")
        topbid_price_currency = topbid_price.get("currency")
        topbid_price_currency_symbol = topbid_price_currency.get("symbol")
        topbid_price_amount = topbid_price.get("amount")
        topbid_price_amount_native = topbid_price_amount.get("native")
        embed.add_field(name="""Top Bid Site""", value=f"```{site}```", inline=True)
        embed.add_field(name="""Top Bid Price""",
                        value=f"```{topbid_price_amount_native} {topbid_price_currency_symbol} ```", inline=True)
    else:
        embed.add_field(name="""Top Bid Site""", value=f"```None```", inline=True)
        embed.add_field(name="""Top Bid Price""", value=f"```None```", inline=True)

    if search_type == 2:
        try:
            data = await fetch_asset_events(contractId)
            df = process_asset_events(data)
            chart_image = await create_price_chart(df, symbol)
            now_in_seconds = time.time()
            now_in_milliseconds = int(now_in_seconds * 1000)
            embed.set_image(
                url=f"{operating_system.getenv('SEARCHFI_BOT_DOMAIN')}/static/{chart_image}?v={now_in_milliseconds}")
        except Exception as e:
            logger.error(f"os set_image error: {e}")
            pass
    else:
        embed.add_field(name="Activity Info", value=sales_list, inline=False)

    embed.add_field(name=f"""Links""", value=f"{projectLinks}", inline=False)
    embed.set_footer(text="Powered by SearchFi DEV")

    await ctx.reply(embed=embed, mention_author=True)


@bot.command()
async def msave(ctx, blockchain, keyword, symbol):
    reg_user = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"
    user_id = ctx.author.id

    Queries.update_keyword(db, blockchain, keyword, symbol, reg_user, user_id)

    embed = Embed(title="Saved", description=f"✅ Keyword `{keyword}` has been saved.\n\n✅ `{keyword}` 키워드가 저장되었습니다.",
                  color=0x37E37B)
    embed.set_footer(text="Powered by SearchFi DEV")
    await ctx.reply(embed=embed, mention_author=True)


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
    'CET': 'Europe/Paris',
    'CEST': 'Europe/Paris',
    'EET': 'Europe/Bucharest',
    'EEST': 'Europe/Bucharest',
    'WET': 'Europe/Western',
    'WEST': 'Europe/Western',
    # Add more if needed
})


@bot.command()
async def mtime(ctx, date_str, time_str, from_tz_param, to_tz_str_param):
    from_tz_str = timezone_mapping.get(from_tz_param.upper())
    to_tz_str = timezone_mapping.get(to_tz_str_param.upper())

    if not from_tz_str or not to_tz_str:
        embed = Embed(title="Error", description=f"❌ Invalid timezone provided.\n\n❌ 시간대가 올바르지 않습니다.", color=0xff0000)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)
        return

    from_tz = pytz.timezone(from_tz_str)
    to_tz = pytz.timezone(to_tz_str)

    datetime_str = date_str + ' ' + time_str

    try:
        from datetime import datetime
        datetime_obj = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
    except ValueError:
        embed = Embed(title="Error",
                      description="❌ Invalid datetime format. Please use `YYYY-MM-DD HH:MM`\n\n❌ 날짜형식이 올바르지 않습니다. `YYYY-MM-DD HH:MM` 형식으로 입력해주세요.",
                      color=0xff0000)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)
        return

    datetime_obj = from_tz.localize(datetime_obj)
    datetime_in_to_tz = datetime_obj.astimezone(to_tz)

    embed = Embed(title="Date Conversion",
                  description=f"```{datetime_str}({from_tz_param.upper()})\n\n🔄\n\n{datetime_in_to_tz.strftime('%Y-%m-%d %H:%M')}({to_tz_str_param.upper()})```",
                  color=0xFEE501)
    embed.set_footer(text="Powered by SearchFi DEV")
    await ctx.reply(embed=embed, mention_author=True)


@bot.command()
async def 해외주식(ctx, stock_symbol: str):
    user = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"

    if not (user == "일론마스크#1576" or user == "으노아부지#2642"):
        embed = Embed(title="NO NO NO!", description="❌ Only for 일론마스크#1576\n\n❌ 오직 일론 형님만 조회 가능합니다!", color=0xff0000)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)
        return

    stock_key = operating_system.getenv("STOCK_KEY")
    BASE_URL = "https://www.alphavantage.co/query"
    params = {
        "function": "TIME_SERIES_DAILY_ADJUSTED",
        "symbol": stock_symbol,
        "apikey": stock_key  # replace with your own API key
    }

    response = requests.get(BASE_URL, params=params)
    data = response.json()

    if 'Time Series (Daily)' not in data:
        embed = Embed(title="Warning",
                      description="ℹ️ Could not fetch the stock data. Please check the stock symbol. This function can be used up to 5 times every 5 minutes.\n\nℹ️ 주식 데이터를 가져올 수 없습니다. 주식 심볼을 확인해주세요. 이 기능은 5분마다 최대 5회까지 사용 가능합니다.",
                      color=0xFFFFFF)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)
        return

    # Convert the time series data into a pandas DataFrame
    df = pd.DataFrame.from_dict(data['Time Series (Daily)'], orient='index', dtype=float)
    df.index = pd.to_datetime(df.index)  # convert index to datetime
    df = df.rename(columns={'1. open': 'Open', '2. high': 'High', '3. low': 'Low', '4. close': 'Close',
                            '6. volume': 'Volume'})  # rename columns
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']]  # rearrange columns

    # Create the plot with the desired style and save it as an image file
    # mc = mpf.make_marketcolors(up='g', down='r', volume='b', inherit=True)
    # s = mpf.make_mpf_style(base_mpf_style='kenan', marketcolors=mc, rc={'xtick.major.pad': 10, 'ytick.major.pad': 5})
    mc = mpf.make_marketcolors(up='#2e7871', down='#e84752', inherit=True)
    s = mpf.make_mpf_style(
        base_mpf_style='nightclouds',
        y_on_right=True,
        marketcolors=mc,
        facecolor='#131722',
        edgecolor='#4a4e59',
        figcolor='#131722',
        gridstyle='solid',
        gridcolor='#1d202b')
    fig, axes = mpf.plot(df, style=s, type='candle', volume=True, title=f"{stock_symbol} Stock Chart", returnfig=True,
                         show_nontrading=True)
    axes[0].yaxis.tick_right()
    axes[0].yaxis.set_label_position("right")
    axes[0].xaxis_date()
    axes[0].xaxis.set_major_formatter(DateFormatter("%Y-%m-%d"))  # New line to format date
    fig.tight_layout()
    fig.savefig('stock_chart.png')
    plt.close(fig)

    await ctx.reply(file=discord.File('stock_chart.png'), mention_author=True)


@bot.command()
async def coin(ctx, coin_symbol: str, period: str = "1day"):
    base_coin = coin_symbol.upper()
    quote_coin = 'USDT'

    symbol = base_coin + quote_coin

    if not re.match('^[A-Z0-9-_.]{1,20}$', symbol):
        embed = Embed(title="Warning",
                      description=f"❌ '{symbol}' is not a valid coin symbol. \n\n❌ '{symbol}'은(는) 유효한 코인 심볼이 아닙니다.",
                      color=0xFFFFFF)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)
        return

    binance_api_key = operating_system.getenv("BINANCE_API_KEY")
    binance_secret_key = operating_system.getenv("BINANCE_SECRET_KEY")
    binance_client = Client(binance_api_key, binance_secret_key)

    if period == "5min" or period == "1day":
        interval = Client.KLINE_INTERVAL_5MINUTE
    else:
        interval = Client.KLINE_INTERVAL_1DAY

    limit = 1000

    try:
        candles = binance_client.get_klines(symbol=symbol, interval=interval, limit=limit)
        # Get the latest ticker information
        ticker = binance_client.get_ticker(symbol=symbol)
    except:
        embed = Embed(title="Warning",
                      description="❌ Invalid symbol. Please check the symbol and try again.\n\n❌ 잘못된 기호입니다. 기호를 확인하고 다시 시도하십시오.",
                      color=0xFFFFFF)
        embed.set_footer(text="Powered by SearchFi DEV")
        await ctx.reply(embed=embed, mention_author=True)
        return

    df = pd.DataFrame(candles,
                      columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close time', 'Quote asset volume',
                               'Number of trades', 'Taker buy base asset volume', 'Taker buy quote asset volume',
                               'Ignore'])
    df['Date'] = pd.to_datetime(df['Date'], unit='ms')
    df.set_index('Date', inplace=True)
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].astype(float)

    df.index = df.index.to_pydatetime()
    df.index = df.index.tz_localize('UTC').tz_convert('Asia/Seoul')

    end_date = df.index.max()
    text_space = 1
    if period is not None:
        if period == "3year":
            start_date = end_date - timedelta(days=3 * 365)
            period_str = "3-Year"
            text_space = 50
        elif period == "1year":
            start_date = end_date - timedelta(days=365)
            period_str = "1-Year"
            text_space = 15
        elif period == "1mon":
            start_date = end_date - timedelta(days=30)
            period_str = "1-Month"
            text_space = 2
        elif period == "3mon":
            start_date = end_date - timedelta(days=90)
            period_str = "3-Month"
            text_space = 5
        elif period == "1week":
            start_date = end_date - timedelta(days=7)
            period_str = "1-Week"
            text_space = 0
        elif period == "1day":
            start_date = end_date - timedelta(days=1)
            period_str = "1-Day (5min interval)"
            text_space = 5
        elif period == "5min":
            start_date = end_date - timedelta(minutes=120)
            period_str = "2-Hour (5min interval)"
            text_space = 1
        else:
            embed = Embed(title="Warning",
                          description="ℹ️ Please enter a valid period: '3year', '1year', '3mon', '1mon', '1week', '1day', '5min' or leave it blank for full data.\n\nℹ️ '3year', '1year', '3mon', '1mon', '1week', '1day', '5min' 형식의 기간을 입력하거나 전체 데이터를 입력하려면 공백으로 두십시오.",
                          color=0xFFFFFF)
            embed.set_footer(text="Powered by SearchFi DEV")
            await ctx.reply(embed=embed, mention_author=True)
            return
    else:
        start_date = end_date - timedelta(days=90)
        period_str = "3-Monthly"

    df = df.loc[(df.index >= start_date) & (df.index <= end_date)]
    df.index = df.index.to_pydatetime()

    # mc = mpf.make_marketcolors(up='g', down='r', volume='b', inherit=True)
    # s = mpf.make_mpf_style(marketcolors=mc)
    mc = mpf.make_marketcolors(up='#2e7871', down='#e84752', inherit=True)
    s = mpf.make_mpf_style(
        base_mpf_style='nightclouds',
        y_on_right=True,
        marketcolors=mc,
        facecolor='#131722',
        edgecolor='#4a4e59',
        figcolor='#131722',
        gridstyle='solid',
        gridcolor='#1d202b')
    fig, axes = mpf.plot(df, type='candle', style=s, volume=True, returnfig=True)

    # fig.suptitle(f"{base_coin} Coin Chart", fontsize=20)

    # Draw current price
    axes[0].axhline(y=float(ticker['lastPrice']), color='white', linestyle='--', linewidth=1)
    axes[0].text(len(df.index) + text_space,
                 float(ticker['lastPrice']),
                 f"{np.format_float_positional(float(ticker['lastPrice']))}",
                 color="white",
                 ha="left",
                 va="center",
                 bbox=dict(facecolor='red', alpha=0.5))

    axes[0].yaxis.tick_right()
    axes[0].yaxis.set_label_position("left")
    axes[0].xaxis_date()
    axes[0].set_ylabel('PRICE (USDT)')
    fig.tight_layout()

    fig.savefig('./static/coin_chart.png', bbox_inches='tight')
    plt.close(fig)

    # response = requests.get('https://api.coingecko.com/api/v3/coins/list')
    # coins = response.json()
    #
    # coin_name = next((coin['name'] for coin in coins if coin['symbol'].upper() == base_coin), base_coin)
    coin_name = f"{base_coin}/{quote_coin}"

    # Extract the necessary information
    last_price = float(ticker['lastPrice'])
    change_24h = float(ticker['priceChange'])
    change_24h_percent = float(ticker['priceChangePercent'])
    change_prefix = '+' if change_24h > 0 else ''
    high_24h = float(ticker['highPrice'])
    low_24h = float(ticker['lowPrice'])
    volume_24h_volume = float(ticker['volume'])
    volume_24h_usdt = float(ticker['quoteVolume'])

    now_in_seconds = time.time()
    now_in_milliseconds = int(now_in_seconds * 1000)

    # Now you can use these values in your code or embed message
    embed = discord.Embed(title=f"{coin_name}", description=f"{coin_name} {period_str} Chart Based on Binance",
                          color=0xEFB90A)
    embed.add_field(name="Last Price", value=f"```{last_price:,.4f}```")
    embed.add_field(name="24h Change",
                    value=f"```diff\n{change_prefix}{change_24h:,.4f} ({change_prefix}{change_24h_percent}%)```")
    embed.add_field(name="24h High", value=f"```{high_24h:,.2f}```")
    embed.add_field(name="24h Low", value=f"```{low_24h:,.2f}```")
    embed.add_field(name=f"24h Volume ({base_coin})", value=f"```{volume_24h_volume:,.2f}```")
    embed.add_field(name="24h Volume (USDT)", value=f"```{volume_24h_usdt:,.2f}```")
    embed.set_image(
        url=f"{operating_system.getenv('SEARCHFI_BOT_DOMAIN')}/static/coin_chart.png?v={now_in_milliseconds}")  # Set the image in the embed using the image URL
    embed.set_footer(text="Powered by SearchFi DEV")
    await ctx.reply(embed=embed, mention_author=True)


@bot.command()
async def coin2(ctx, coin_symbol: str):
    COINMARKETCAP_API_KEY = operating_system.getenv("COINMARKETCAP_API_KEY")

    url = f'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest?symbol={coin_symbol.upper()}&convert=USDT'
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': COINMARKETCAP_API_KEY,
    }
    parameters = {
        'symbol': coin_symbol.upper()
    }

    response = requests.get(url, headers=headers)
    data = response.json()

    if response.status_code == 200 and data['status']['error_code'] == 0:
        coin_info = data['data'][coin_symbol.upper()]['quote']['USDT']

        embed = discord.Embed(
            title=f"{coin_symbol.upper()} Information",
            description=f"{coin_symbol.upper()} Price and Statistics",
            color=0x00ff00
        )
        embed.add_field(name="Last Price", value=f"```python\n{coin_info['price']:,.4f} USDT```")
        embed.add_field(name="1h Change",
                        value=f"```diff\n{'+' if coin_info['percent_change_1h'] > 0 else ''}{coin_info['percent_change_1h']:,.2f}%```")
        embed.add_field(name="24h Change",
                        value=f"```diff\n{'+' if coin_info['percent_change_24h'] > 0 else ''}{coin_info['percent_change_24h']:,.2f}%```")
        embed.add_field(name="7d Change",
                        value=f"```diff\n{'+' if coin_info['percent_change_7d'] > 0 else ''}{coin_info['percent_change_7d']:,.2f}%```")
        embed.add_field(name="30d Change",
                        value=f"```diff\n{'+' if coin_info['percent_change_30d'] > 0 else ''}{coin_info['percent_change_30d']:,.2f}%```")
        embed.add_field(name="60d Change",
                        value=f"```diff\n{'+' if coin_info['percent_change_60d'] > 0 else ''}{coin_info['percent_change_60d']:,.2f}%```")
        embed.add_field(name="90d Change",
                        value=f"```diff\n{'+' if coin_info['percent_change_90d'] > 0 else ''}{coin_info['percent_change_90d']:,.2f}%```")
        embed.add_field(name="Market Cap", value=f"```python\n{coin_info['market_cap']:,.2f} USDT```")
        embed.add_field(name="Volume (24h)", value=f"```python\n{coin_info['volume_24h']:,.2f} USDT```")
        embed.set_footer(text="Powered by SearchFi DEV")

        await ctx.send(embed=embed)
    else:
        embed = Embed(title="Warning",
                      description="❌ Invalid symbol. Please check the symbol and try again.\n\n❌ 잘못된 기호입니다. 기호를 확인하고 다시 시도하십시오.",
                      color=0xFFFFFF)
        embed.set_footer(text="Powered by SearchFi DEV")


@bot.command()
async def 김프(ctx):
    # Upbit
    url = "https://api.upbit.com/v1/ticker?markets=KRW-USDT"
    headers = {
        'Accepts': 'application/json'
    }

    response = requests.get(url, headers=headers)
    data = response.json()
    # print(data)

    usdt_list = []
    if response.status_code == 200:
        usdt = data[0].get("trade_price")
        usdt_list.append({
            "name": "Upbit     (USDT)",
            "price": float(usdt)
        })

    # Bithumb
    url = "https://api.bithumb.com/public/ticker/USDT_KRW"
    headers = {
        'Accepts': 'application/json'
    }

    response = requests.get(url, headers=headers)
    data = response.json()
    # print(data)

    if response.status_code == 200:
        usdt = data.get("data").get("closing_price")
        usdt_list.append({
            "name": "Bithumb   (USDT)",
            "price": float(usdt)
        })

    # Coinone(USDT)
    url = "https://api.coinone.co.kr/public/v2/ticker_utc_new/KRW/USDT?additional_data=true"
    headers = {
        'Accepts': 'application/json'
    }

    response = requests.get(url, headers=headers)
    data = response.json()
    # print(data)

    if response.status_code == 200:
        usdt = data.get("tickers")[0].get("last")
        usdt_list.append({
            "name": "Coinone   (USDT)",
            "price": float(usdt)
        })

    # Coinone(USDC)
    url = "https://api.coinone.co.kr/public/v2/ticker_utc_new/KRW/USDC?additional_data=true"
    headers = {
        'Accepts': 'application/json'
    }

    response = requests.get(url, headers=headers)
    data = response.json()
    # print(data)

    if response.status_code == 200:
        usdt = data.get("tickers")[0].get("last")
        usdt_list.append({
            "name": "Coinone   (USDC)",
            "price": float(usdt)
        })

    # Korbit
    url = "https://api.korbit.co.kr/v1/ticker?currency_pair=usdt_krw"
    headers = {
        'Accepts': 'application/json'
    }

    response = requests.get(url, headers=headers)
    data = response.json()
    # print(data)

    if response.status_code == 200:
        usdt = data.get("last")
        usdt_list.append({
            "name": "Korbit    (USDT)",
            "price": float(usdt)
        })

    # Gopax
    url = "https://api.gopax.co.kr/trading-pairs/USDT-KRW/ticker"
    headers = {
        'Accepts': 'application/json'
    }

    response = requests.get(url, headers=headers)
    data = response.json()
    # print(data)

    if response.status_code == 200:
        usdt = data.get("price")
        usdt_list.append({
            "name": "Gopax     (USDT)",
            "price": float(usdt)
        })

    # KRW-USDT
    ex_api_key = operating_system.getenv("EXCHANGERATE_API_KEY")
    exchange_rate_api_url = f"https://v6.exchangerate-api.com/v6/{ex_api_key}/latest/USD"

    response = requests.get(exchange_rate_api_url)
    if response.status_code != 200:
        await ctx.send("Error getting exchange rates.")
        return
    exchange_rates = response.json()['conversion_rates']
    usdt_krw = exchange_rates['KRW']
    # print(usdt_krw)

    if usdt_list:
        embed = discord.Embed(
            title=f"Current USD/KRW: **{round(usdt_krw, 2)} KRW**",
            description=f"Exchange USDT Information",
            color=0xEFB90A
        )
        for usdt in usdt_list:
            price = usdt.get('price')
            rate = (price - usdt_krw) / usdt_krw * 100
            if rate > 0:
                flag = f"+"
            else:
                flag = ""
            embed.add_field(name=f"{usdt.get('name')}",
                            value=f"```diff\n{flag}{{:,.1f}}%\n{{:,.2f}} KRW```".format(rate, price), inline=True)

        await ctx.send(embed=embed)
    else:
        embed = Embed(title="Warning",
                      description="❌ Invalid symbol. Please check the symbol and try again.\n\n❌ 잘못된 기호입니다. 기호를 확인하고 다시 시도하십시오.",
                      color=0xFFFFFF)
        embed.set_footer(text="Powered by SearchFi DEV")


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Super', 'SF.Guardian', 'SF.dev')
async def addrole(ctx, sheet_name, role_name):
    # 결과를 저장할 문자열을 초기화합니다.
    result_str = ""

    try:
        # 구글 시트 접근 설정
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
                 "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name('searchfi.json', scope)
        client = gspread.authorize(creds)

        # 시트 열기
        sheet = client.open(sheet_name).sheet1
        user_list = sheet.get_all_records()

        guild = ctx.guild
        role = discord.utils.get(guild.roles, name=role_name)

        total_count = len(user_list)
        processed_count = 0

        for user_info in user_list:
            if 'discord_uid' in user_info:
                try:
                    uid = int(user_info['discord_uid'])
                except ValueError:
                    result_str += f"UID {user_info['discord_uid']}은(는) 유효한 숫자 형식이 아닙니다.\n"
                    continue

                member = guild.get_member(uid)

                if member is not None:
                    result_str += f"{member.name}#{member.discriminator} (UID: {member.id}) 님에게 {role_name} 롤을 부여했습니다.\n"
                    await member.add_roles(role)
                else:
                    result_str += f"UID {uid}의 사용자는 서버에 없습니다.\n"

            processed_count += 1

            # 500명마다 진행 상태를 업데이트합니다. 마지막 사용자도 처리합니다.
            if processed_count % 500 == 0 or processed_count == total_count:
                await ctx.send(f"진행률: {processed_count}/{total_count} ({(processed_count / total_count) * 100:.2f}%)")

        # 결과를 txt 파일로 저장합니다.
        with open('result.txt', 'w') as f:
            f.write(result_str)

        await ctx.send(file=discord.File('result.txt'))

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        await ctx.send(f"오류가 발생했습니다: {str(e)}")

    await ctx.send("사용자 확인을 완료했습니다.")


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def removerole(ctx, role_name):
    try:
        # 결과를 저장할 문자열을 초기화합니다.
        result_str = ""

        guild = ctx.guild  # 현재 채팅창의 길드를 가져옵니다.
        role = discord.utils.get(guild.roles, name=role_name)  # 특정 역할을 가져옵니다.

        if role is None:
            await ctx.send(f"{role_name} 역할은 서버에 없습니다.")
            return

        member_count = len(guild.members)
        processed_count = 0

        # 길드의 모든 멤버를 반복하면서 역할이 있는 멤버를 찾습니다.
        for member in guild.members:
            if role in member.roles:
                await member.remove_roles(role)  # 역할을 제거합니다.
                result_str += f"{member.name}#{member.discriminator} 님에게서 {role_name} 역할을 제거했습니다.\n"

            processed_count += 1

            # 5000명마다 진행 상태를 업데이트합니다. 마지막 멤버도 처리합니다.
            if processed_count % 5000 == 0 or processed_count == member_count:
                await ctx.send(f"진행률: {processed_count}/{member_count} ({(processed_count / member_count) * 100:.2f}%)")

        # 결과를 txt 파일로 저장합니다.
        with open('remove_result.txt', 'w') as f:
            f.write(result_str)

        # 파일을 메시지로 첨부하여 보냅니다.
        await ctx.send(file=discord.File('remove_result.txt'))

    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        await ctx.send(f"오류가 발생했습니다: {str(e)}")

    # 완료 메시지를 보냅니다.
    await ctx.send(f"{role_name} 역할 제거를 완료했습니다.")


@bot.command()
async def 나무(ctx):
    embed = Embed(title="SearchFi 나무위키", description="https://namu.wiki/w/SearchFi", color=0xFFFFFF)
    await ctx.reply(embed=embed, mention_author=True)


@bot.command()
async def ai(ctx, count="0", *prompts):
    await draw(ctx, count, *prompts)


@bot.command()
async def ai2(ctx):
    if len(ctx.message.attachments) == 0:
        await ctx.reply("No image provided. Please attach an image.")
        return

    random_color = random.randint(0, 0xFFFFFF)

    embed = Embed(title="SearchFi AI Image Edit Bot", color=random_color)
    embed.set_footer(text="Editing images...")
    await ctx.send(embed=embed)

    # Download the image from the attachment
    attachment = ctx.message.attachments[0]
    temp_uuid = uuid.uuid4()  # Generate a random UUID for the temporary image file
    image_path = f"./{temp_uuid}.png"  # Use the UUID as the file name to prevent duplication
    await attachment.save(image_path)

    # Open the image file and convert it to 'RGBA'
    image = Image.open(image_path).convert('RGBA')
    image.save(image_path)

    # Use the image to create a new image
    try:
        with open(image_path, "rb") as image_file:
            response = client.images.create_variation(
                image=image_file.read(),
                n=1,
                size="1024x1024"
            )

        image_url = response['data'][0]['url']

        embed = Embed(title="Image Edit", color=random_color)
        embed.set_image(url=image_url)
        await ctx.reply(embed=embed, mention_author=True)

    finally:
        # Remove the temporary image file after the new image has been created
        if operating_system.path.exists(image_path):
            operating_system.remove(image_path)


def imageToString(img):
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    my_encoded_img = base64.encodebytes(img_byte_arr.getvalue()).decode('ascii')
    return my_encoded_img


@bot.command()
async def draw(ctx, count="0", *prompts):
    random_color = random.randint(0, 0xFFFFFF)

    try:
        count = int(count)
    except:
        error_embed = Embed(title="Error", description="Enter 1 to 4 images to create.\n\n생성할 이미지 개수를 1~4까지 입력하세요.",
                            color=0xFF0000)
        await ctx.reply(embed=error_embed, mention_author=True)
        return

    if count == 0 or count > 4:
        error_embed = Embed(title="Error", description="Enter 1 to 4 images to create.\n\n생성할 이미지 개수를 1~4까지 입력하세요.",
                            color=0xFF0000)
        await ctx.reply(embed=error_embed, mention_author=True)
        return

    if len(prompts) == 0:
        error_embed = Embed(title="Error",
                            description="No prompt provided. Please provide a prompt.\n\n프롬프트가 입력되지 않습니다. 프롬프트를 입력하십시오.",
                            color=0xFF0000)
        await ctx.reply(embed=error_embed, mention_author=True)
        return

    embed = Embed(title="SearchFi AI Image Gen Bot", color=random_color)
    embed.set_footer(text="Generating images...")
    await ctx.send(embed=embed)

    prompt_text = " ".join(prompts)
    model = "gpt-3.5-turbo"

    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant who is good at translating."
        },
        {
            "role": "user",
            "content": f"```{prompt_text}```\n\nPlease translate the above sentence directly into English.\n\nIf the sentence is English, please print it out as it is."
        }
    ]

    # ChatGPT API 호출하기
    response = client.chat.completions.create(
        model=model,
        messages=messages
    )
    answer = response.choices[0].message.content
    print(answer)

    try:
        # 프롬프트에 사용할 제시어
        prompt = answer
        negative_prompt = ""
        seeds = []
        seed = random.randint(0, 4294967291)

        for index in range(count):
            seeds.append(seed + index)

        # [내 애플리케이션] > [앱 키] 에서 확인한 REST API 키 값 입력
        REST_API_KEY = operating_system.getenv("KARLO_API_KEY")

        r = requests.post(
            'https://api.kakaobrain.com/v2/inference/karlo/t2i',
            json={
                'prompt': prompt,
                'width': 512,
                'height': 512,
                'samples': count,
                'image_quality': 70,
                'guidance_scale': 12.5,
                'num_inference_steps': 20,
                'seed': seeds
            },
            headers={
                'Authorization': f'KakaoAK {REST_API_KEY}',
                'Content-Type': 'application/json'
            }
        )
        # 응답 JSON 형식으로 변환
        response = json.loads(r.content)

        img_arr = []

        for i in range(count):
            img = Image.open(urllib.request.urlopen(response.get("images")[i].get("image")))
            img_base64 = image_to_string(img)
            img_arr.append(img_base64)

        r = requests.post(
            'https://api.kakaobrain.com/v2/inference/karlo/upscale',
            json={
                'images': img_arr,
                'scale': 2,
                'image_quality': 100
            },
            headers={
                'Authorization': f'KakaoAK {REST_API_KEY}',
                'Content-Type': 'application/json'
            }
        )
        # 응답 JSON 형식으로 변환
        response = json.loads(r.content)
        # print(response)

        # 응답의 첫 번째 이미지 생성 결과 출력하기
        image_urls = [img for img in response.get("images")]
        # image_urls = [img["image"] for img in response.get("images")]
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        error_embed = Embed(title="Error", description="An unexpected error occurred.\n\n예기치 않은 오류가 발생했습니다.",
                            color=0xFF0000)
        await ctx.reply(embed=error_embed, mention_author=True)
        return

    index = 0
    for image_url in image_urls:
        index += 1
        embed = Embed(title=f"Image {index}", color=random_color)
        embed.set_image(url=image_url)
        embed.set_footer(text=f"Image {index} generation complete")
        await ctx.send(embed=embed)

    embed = Embed(title="All Image generation complete", color=random_color)
    await ctx.reply(embed=embed, mention_author=True)


@bot.command()
async def 챗(ctx, *prompts):
    await gpt(ctx, *prompts)


@bot.command()
async def gpt(ctx, *prompts):
    user_id = ctx.message.author.id

    if len(prompts) == 0:
        error_embed = Embed(title="Error",
                            description="No prompt provided. Please provide a prompt.\n\n프롬프트가 입력되지 않습니다. 프롬프트를 입력하십시오.",
                            color=0xFF0000)
        await ctx.reply(embed=error_embed, mention_author=True)
        return

    random_color = random.randint(0, 0xFFFFFF)

    embed = Embed(title="SearchFi AI Chat Bot", color=random_color)
    embed.set_footer(text="Waiting for an answer...")
    await ctx.send(embed=embed)

    prompt_text = " ".join(prompts)

    # Load previous context for the current user
    previous_context = Queries.select_message(db, user_id)

    # If the user has sent messages before
    if previous_context:
        # Get the timestamp of the last message
        last_message_time = previous_context[-1]['timestamp']

        # Check if the user is sending a query within 5 seconds
        if datetime.datetime.now() - last_message_time < datetime.timedelta(seconds=10):
            error_embed = Embed(title="Error",
                                description="You are sending queries too fast. Please wait a few seconds.\n\n질문을 너무 빠르게 보내고 있습니다. 몇 초 기다려 주세요.",
                                color=0xFF0000)
            await ctx.reply(embed=error_embed, mention_author=True)
            return

    try:
        messages_with_timestamps = previous_context
        messages_for_openai = [{"role": m["role"], "content": m["content"]} for m in messages_with_timestamps]

        messages = [
                       {"role": "system", "content": "You are a helpful assistant in SearchFi Community."},
                   ] \
                   + [
                       {"role": "user",
                        "content": "서치파이는 NFT DAO 커뮤니티입니다.\n\n프로젝트 탐색 및 연구를 기반으로 생태계를 확장하는 것이 목표입니다.\n\n디스코드 내에서 서비스를 운영하고 있으며 한국어, 영어, 일본어, 중국어 채널이 따로 있을 만큼 해외 이용자 수가 많습니다.\n\n팀원은 12명으로 CEO는 이정진이며, 그의 트위터는 @eth_apple 입니다."}
                   ] \
                   + [
                       {"role": "user",
                        "content": "SearchFi is an NFT DAO community.\n\nThe goal is to expand the ecosystem based on project exploration and research.\n\nWe operate the service within Discord and have a large number of overseas users, with separate Korean, English, Japanese, and Chinese channels.\n\nThere are 12 team members, CEO Lee Jung-jin, and his Twitter account is @eth_apple."}
                   ] \
                   + messages_for_openai \
                   + [
                       {"role": "user", "content": f"{prompt_text}\n\nAnswers up to 600 characters."},
                   ]

        min = 3
        max = len(messages)
        if max > 0:
            while min < max:
                # print(min, max)
                if len(str(messages[0:2] + messages[min:max])) < 4097:
                    messages = messages[0:2] + messages[min:max]
                    break
                min += 1

        # print(messages)
        # print(len(str(messages)))

        result = client.chat.completions.create(
            model=model,
            messages=messages
        )
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        error_embed = Embed(title="Error", description="Failed to get a response from AI.\n\nAI로부터 응답을 받지 못했습니다.",
                            color=0xFF0000)
        await ctx.reply(embed=error_embed, mention_author=True)
        return

    if result and len(result.choices) > 0:
        assistant_response = result.choices[0].message.content
        embed = Embed(title="SearchFi AI Answer", description=assistant_response, color=random_color)
        await ctx.reply(embed=embed, mention_author=True)

        # Save user's message to the DB
        Queries.insert_message(db, user_id, "user", prompt_text)

        # Save AI's message to the DB
        Queries.insert_message(db, user_id, "assistant", assistant_response)
    else:
        error_embed = Embed(title="Error", description="Failed to get a response from AI.\n\nAI로부터 응답을 받지 못했습니다.",
                            color=0xFF0000)
        await ctx.reply(embed=error_embed, mention_author=True)


@bot.command()
async def calc(ctx, *prompts):
    operating_system.environ["OPENAI_API_KEY"] = operating_system.getenv("OPENAI_SECRET_KEY")
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)
    llm_math_chain = LLMMathChain(llm=llm, verbose=True)
    tools = [
        Tool(
            name="Math",
            func=llm_math_chain.invoke,
            description="Useful when you need to calculate questions about the current event"
        ),
    ]

    user_id = ctx.message.author.id

    if len(prompts) == 0:
        error_embed = Embed(title="Error",
                            description="No prompt provided. Please provide a prompt.\n\n프롬프트가 입력되지 않습니다. 프롬프트를 입력하십시오.",
                            color=0xFF0000)
        await ctx.reply(embed=error_embed, mention_author=True)
        return

    random_color = random.randint(0, 0xFFFFFF)

    embed = Embed(title="SearchFi AI Calculator Bot", color=random_color)
    embed.set_footer(text="Waiting for an answer...")
    await ctx.send(embed=embed)

    prompt_text = " ".join(prompts)

    # Load previous context for the current user
    previous_context = Queries.select_message(db, user_id)

    # If the user has sent messages before
    if previous_context:
        # Get the timestamp of the last message
        last_message_time = previous_context[-1]['timestamp']

        # Check if the user is sending a query within 5 seconds
        if datetime.datetime.now() - last_message_time < datetime.timedelta(seconds=10):
            error_embed = Embed(title="Error",
                                description="You are sending queries too fast. Please wait a few seconds.\n\n질문을 너무 빠르게 보내고 있습니다. 몇 초 기다려 주세요.",
                                color=0xFF0000)
            await ctx.reply(embed=error_embed, mention_author=True)
            return

    try:
        agent = initialize_agent(tools, llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=True)
        messages = agent.run(prompt_text)
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        error_embed = Embed(title="Error", description="Failed to get a response from AI.\n\nAI로부터 응답을 받지 못했습니다.",
                            color=0xFF0000)
        await ctx.reply(embed=error_embed, mention_author=True)
        return

    if messages:
        print(messages)
        assistant_response = messages
        embed = Embed(title="SearchFi AI Answer", description=assistant_response, color=random_color)
        await ctx.reply(embed=embed, mention_author=True)

        # Save user's message to the DB
        Queries.insert_message(db, user_id, "user", prompt_text)

        # Save AI's message to the DB
        Queries.insert_message(db, user_id, "assistant", assistant_response)
    else:
        error_embed = Embed(title="Error", description="Failed to get a response from AI.\n\nAI로부터 응답을 받지 못했습니다.",
                            color=0xFF0000)
        await ctx.reply(embed=error_embed, mention_author=True)


@bot.command()
async def mstats(ctx):
    results = Queries.select_stats(db)

    num_pages = (len(results) + 9) // 10

    pages = []

    for page in range(num_pages):
        description = "```\n📅 : Project REG Count (2 Point)\n"
        description += "✅ : Project CHECKER Count (1.5 Point)\n"
        description += "📢 : Project Call Count (1.5 Point)\n"
        description += "👍 : Project UP Count (0.1 Point)\n"
        description += "👎 : Project DOWN Count (0.1 Point)\n\n```"

        embed = Embed(title=f"**🏆 Project REG / CHECKER / CALL / UP / DOWN Ranking 🏆**\n\n"
                            f"Top {page * 10 + 1} ~ {page * 10 + 10} Rank\n", description=f"{description}",
                      color=0x00ff00)

        field_value = "```\n"

        for i in range(10):
            index = page * 10 + i
            if index >= len(results):
                break

            item = results[index]
            print(int(item['user_id']))
            user = bot.get_user(int(item['user_id']))
            field_value += "{:>4s}{:<6s}{:<6s}{:<6s}{:<6s}{:<6s}{:<20s}\n".format(
                f"{item['ranking']}. ",
                f"📅 {item['REG']}",
                f"✅ {item['CHECKER']}",
                f"📢 {item['SEARCHFI_CALL']}",
                f"👍 {item['UP']}",
                f"👎 {item['DOWN']}",
                f"@{user}",
            )

        field_value += "```"
        embed.add_field(name="", value=field_value, inline=False)
        embed.set_footer(text=f"by SearchFI Bot")

        # cal = Page(content=f"**🏆 Project REG / CHECKER / CALL / UP / DOWN Ranking 🏆**", embed=embed)
        pages.append(embed)

    paginator = Paginator(pages=pages)
    await paginator.send(ctx, mention_author=True)


@bot.command()
async def 타로(ctx):
    await tarot(ctx)


def get_card_frame(index):
    filepath = "tarot-cards-slide-show.gif"
    img = Image.open(filepath)
    if img.is_animated:
        frames = [frame.copy() for frame in ImageSequence.Iterator(img)]
        return frames[index]
    return None


@bot.command()
async def tarot(ctx):
    user_id = ctx.message.author.id
    regUser = f"{ctx.message.author.name}#{ctx.message.author.discriminator}"
    current_date = datetime.date.today()

    now_in_seconds = time.time()
    now_in_milliseconds = int(now_in_seconds * 1000)

    result = Queries.select_tarots(db, user_id)

    if result and current_date <= result['draw_date']:
        keyword = Queries.select_keyword(db, f"tarot{result['card_index']}")

        # If the user has drawn today, just send the previous draw
        filename = f"{result['card_index']}.jpg"

        embed = discord.Embed(title=f"{regUser} Today`s Tarot", description=f"{keyword['symbol']}",
                              color=random.randint(0, 0xFFFFFF))
        embed.set_image(
            url=f"{operating_system.getenv('SEARCHFI_BOT_DOMAIN')}/static/{filename}?v={now_in_milliseconds}")  # Set the image in the embed using the image URL
        await ctx.reply(embed=embed, mention_author=True)
    else:
        # Else, make a new draw
        random_color = random.randint(0, 0xFFFFFF)
        frame_index = random.randint(0, 77)
        filename = f"{frame_index}.jpg"

        keyword = Queries.select_keyword(db, f"tarot{frame_index}")

        embed = discord.Embed(title=f"{regUser} Today`s Tarot", description=f"{keyword['symbol']}", color=random_color)
        embed.set_image(
            url=f"{operating_system.getenv('SEARCHFI_BOT_DOMAIN')}/static/{filename}?v={now_in_milliseconds}")  # Set the image in the embed using the image URL

        Queries.insert_tarots(db, user_id, current_date, frame_index)

        await ctx.reply(embed=embed, mention_author=True)


@bot.command()
async def mp(ctx, symbol: str, amount: float):
    ex_api_key = operating_system.getenv("EXCHANGERATE_API_KEY")
    binance_api_url = "https://api.binance.com/api/v3/ticker/price"
    exchange_rate_api_url = f"https://v6.exchangerate-api.com/v6/{ex_api_key}/latest/USD"

    # Get coin price in USD from Binance API
    response = requests.get(binance_api_url, params={"symbol": symbol.upper() + "USDT"})
    if symbol.upper() == "USDT":
        coin_price_in_usd = 1.0
    elif response.status_code != 200:
        await ctx.send("Invalid coin symbol.")
        return
    else:
        coin_price_in_usd = float(response.json()['price'])

    # Get exchange rates
    response = requests.get(exchange_rate_api_url)
    if response.status_code != 200:
        await ctx.send("Error getting exchange rates.")
        return
    exchange_rates = response.json()['conversion_rates']

    # Convert amount to different currencies
    usd_amount = coin_price_in_usd * amount
    result = {
        "USD": usd_amount,
        "KRW": usd_amount * exchange_rates['KRW'],
        "CNY": usd_amount * exchange_rates['CNY'],
        "JPY": usd_amount * exchange_rates['JPY']
    }

    embed = discord.Embed(title=f"{amount} {symbol.upper()} is equal to:", color=0xEFB90A)

    embed.add_field(name="🇺🇸 USA", value="```{:,.2f} USD```".format(result['USD']), inline=False)
    embed.add_field(name="🇰🇷 SOUTH KOREA", value="```{:,.2f} KRW```".format(result['KRW']), inline=False)
    embed.add_field(name="🇨🇳 CHINA", value="```{:,.2f} CNY```".format(result['CNY']), inline=False)
    embed.add_field(name="🇯🇵 JAPAN", value="```{:,.2f} JPY```".format(result['JPY']), inline=False)

    await ctx.send(embed=embed)


def get_gas_prices():
    ETHERSCAN_API_KEY = operating_system.getenv("ETHERSCAN_API_KEY")
    params = {
        'module': 'gastracker',
        'action': 'gasoracle',
        'apikey': ETHERSCAN_API_KEY
    }
    ETHERSCAN_API_URL = "https://api.etherscan.io/api"
    response = requests.get(ETHERSCAN_API_URL, params=params)
    data = response.json()

    return data['result']


def get_current_eth_price():
    # 바이낸스 API 엔드포인트
    binance_api_url = 'https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT'

    try:
        response = requests.get(binance_api_url)
        response.raise_for_status()  # 오류가 발생하면 예외를 발생시킴
        data = response.json()
        return float(data['price'])
    except requests.exceptions.HTTPError as err:
        print(f"HTTP error occurred: {err}")
    except Exception as err:
        print(f"An error occurred: {err}")


@bot.command()
async def g(ctx):
    gas_prices = get_gas_prices()
    current_eth_price = get_current_eth_price()

    fast = float(gas_prices['FastGasPrice'])
    average = float(gas_prices['ProposeGasPrice'])
    slow = float(gas_prices['SafeGasPrice'])

    eth_fast = round(fast * 21000 / 1e9 * current_eth_price, 2)
    eth_average = round(average * 21000 / 1e9 * current_eth_price, 2)
    eth_slow = round(slow * 21000 / 1e9 * current_eth_price, 2)
    transaction_list = "```"
    transaction_list += "{:<18s}{:<8s}{:<9s}{:<9s}\n".format("Action", "Low", "Average", "Fast")
    transaction_list += "-" * 42 + "\n"
    transaction_list += "{:<18s}{:<8s}{:<9s}{:<9s}\n".format(
        "ETH transaction",
        f"${eth_fast:.2f}",
        f"${eth_average:.2f}",
        f"${eth_slow:.2f}",
    )
    transaction_list += "```"

    embed = discord.Embed(title="Gas Estimation",
                          description="Current gas price and estimated transaction fees",
                          color=0xEFB90A)
    embed.add_field(name="😆 Low", value=f"```python\n{slow} GWEI```", inline=True)
    embed.add_field(name="😃 Average", value=f"```python\n{average} GWEI```", inline=True)
    embed.add_field(name="🙂 Fast", value=f"```python\n{fast} GWEI```", inline=True)
    embed.add_field(name="ETH transaction",
                    value=f"{transaction_list}", inline=False)
    embed.set_footer(text="Powered by SearchFi DEV")

    await ctx.send(embed=embed)


def get_current_price(token):
    url = f"https://api.bithumb.com/public/ticker/{token}_KRW"
    headers = {"accept": "application/json"}
    response = requests.get(url, headers=headers)
    data = response.json()

    if data["status"] == "0000":
        return float(data["data"]["closing_price"])
    else:
        return None


def format_time_difference(sale_time):
    # 현재 시간과 판매 시간의 차이를 계산
    elapsed_time = datetime.datetime.now(datetime.timezone.utc) - sale_time

    # 시간 차이를 초 단위로 계산
    total_seconds = int(elapsed_time.total_seconds())

    # 시간 차이를 문자열로 포맷팅
    if total_seconds < 60:  # less than a minute
        return f"{total_seconds}초 전"
    elif total_seconds < 3600:  # less than an hour
        return f"{total_seconds // 60}분 전"
    else:  # show in hours
        return f"{total_seconds // 3600}시간 전"


def fetch_and_format_sales(activities):
    index = 1
    sales = []
    for sale in activities:
        if index > 5:
            break
        try:
            name = sale['token']['meta']['name']
        except:
            name = f"Inscription #{sale['token']['inscriptionNumber']}"
        price = float(sale['listedPrice']) / 100000000
        sale_time = datetime.datetime.strptime(sale['createdAt'], "%a, %d %b %Y %H:%M:%S GMT")
        sale_time = sale_time.replace(tzinfo=timezone.utc)
        elapsed_time = datetime.datetime.now(tz=timezone.utc) - sale_time

        if elapsed_time < timedelta(minutes=1):
            time_string = f"{elapsed_time.seconds} sec ago"
        elif elapsed_time < timedelta(hours=1):
            time_string = f"{elapsed_time.seconds // 60} min ago"
        elif elapsed_time < timedelta(days=1):
            time_string = f"{elapsed_time.seconds // 3600} hrs ago"
        elif elapsed_time < timedelta(days=30):
            time_string = f"{elapsed_time.days} days ago"
        else:
            months_elapsed = elapsed_time.days // 30
            time_string = f"{months_elapsed} months ago"

        sales.append({
            "Name": name,
            "Price": price,
            "Time": time_string
        })
        index += 1
    return sales


def create_table(formatted_sales):
    output = "```\n"
    output += "{:<24s}{:<10s}{:<10s}\n".format("Name", "Price", "Time")
    output += "-" * 44 + "\n"  # 24 characters + 10 characters + 10 characters

    for row in formatted_sales:
        # print(row, len(row.values()))  # 각 행과 그에 해당하는 값의 개수를 출력
        output += "{:<24s}{:<10.5f}{:<10s}\n".format(*row.values())

    output += "```"

    return output


def image_to_string(img):
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    my_encoded_img = base64.encodebytes(img_byte_arr.getvalue()).decode('ascii')
    return my_encoded_img


# Web3 설정
web3 = Web3(Web3.HTTPProvider('https://ethereum.publicnode.com'))

# 컨트랙트 주소를 체크섬 주소로 변환
contract_address = Web3.to_checksum_address('0x7fb2d396a3cc840f2c4213f044566ed400159b40')

# 컨트랙트 ABI (soulbound 함수만 포함)
contract_abi = [
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "soulbound",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    }
]

contract = web3.eth.contract(address=contract_address, abi=contract_abi)


@bot.command()
async def jirasan(ctx, token_id: int):
    try:
        result = contract.functions.soulbound(token_id).call()
        if result:
            await ctx.send(f"```diff\n"
                           f"-Token ID {token_id}는 Lock입니다."
                           f"```")
        else:
            await ctx.send(f"```diff\n"
                           f"+Token ID {token_id}는 Lock이 아닙니다."
                           f"```")
    except Exception as e:
        await ctx.send(f"오류 발생: {str(e)}")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # investment_category_id = int(operating_system.getenv("INVESTMENT_CATEGORY_ID"))
    # allowed_channels = [
    #     1215148551441485904,
    #     974946294068043826,
    #     1072435483466014730
    # ]

    # if message.channel.category_id == investment_category_id or message.channel.id in allowed_channels:
    #     if len(message.content.strip()) != 0:
    #         translator = deepl.Translator(deepl_api_key)
    #         to_language, _ = langid.classify(message.content)
    #         if to_language == "en":
    #             from_language1 = "KO"
    #             from_language2 = "ZH"
    #             language1_name = "Korean"
    #             language2_name = "Chinese"
    #         elif to_language == "ko":
    #             from_language1 = "EN-US"
    #             from_language2 = "ZH"
    #             language1_name = "English"
    #             language2_name = "Chinese"
    #         else:
    #             from_language1 = "KO"
    #             from_language2 = "EN-US"
    #             language1_name = "Korean"
    #             language2_name = "English"
    #
    #         prompt_text: str = message.content
    #
    #         answer1 = translator.translate_text(prompt_text, target_lang=from_language1)
    #         await asyncio.sleep(2)
    #         answer2 = translator.translate_text(prompt_text, target_lang=from_language2)
    #
    #         answer = f"- {language1_name}: {answer1}\n\n" \
    #                  f"- {language2_name}: {answer2}"
    #
    #         await message.channel.send(f"**[AI Translation]**\n{answer}", reference=message)

    sharing_channel_id = int(operating_system.getenv('SHARING_CHANNEL_ID'))
    proof_channel_id = int(operating_system.getenv('PROOF_CHANNEL_ID'))
    proof_backup_channel_id = int(operating_system.getenv('PROOF_BACKUP_CHANNEL_ID'))
    exclude_role_list = list(map(int, operating_system.getenv('C2E_EXCLUDE_ROLE_LIST').split(',')))
    if (
        message.channel.id != sharing_channel_id
        and message.channel.id != proof_channel_id
    ) or any(role.id in exclude_role_list for role in message.author.roles):
        await bot.process_commands(message)
        return
    else:
        # 첨부 파일이 이미지인지 확인
        image_attached = any(attachment.content_type.startswith('image/') for attachment in message.attachments if
                             attachment.content_type)

        if message.channel.id == sharing_channel_id:
            # 메시지에 이미지 첨부 파일과 텍스트가 모두 포함되어 있는지 검사
            if not image_attached or len(message.content.strip()) == 0:
                await message.delete()  # 조건을 만족하지 않으면 메시지 삭제
                # 사용자에게 규칙을 알리는 메시지를 보냄
                warning_msg = await message.channel.send(
                    f"{message.author.mention}, please post both an image and some text together!"
                )
                await warning_msg.delete(delay=10)  # 경고 메시지는 5초 후 자동 삭제
                return
        elif message.channel.id == proof_channel_id:
            # 메시지에 이미지 첨부 파일이 포함되어 있는지 검사
            if not image_attached:
                await message.delete()  # 조건을 만족하지 않으면 메시지 삭제
                # 사용자에게 규칙을 알리는 메시지를 보냄
                warning_msg = await message.channel.send(
                    f"{message.author.mention}, please post an proof image!"
                )
                await warning_msg.delete(delay=10)  # 경고 메시지는 5초 후 자동 삭제
                return
            else:
                # 인증 채널의 모든 메시지를 가져와 예전 업로드 이력이 있는지 체크.
                async for history_message in bot.get_channel(proof_channel_id).history(limit=None, oldest_first=True):
                    if message != history_message and message.author == history_message.author:
                        print(history_message)
                        await message.delete()  # 조건을 만족하지 않으면 메시지 삭제
                        # 사용자에게 규칙을 알리는 메시지를 보냄
                        warning_msg = await message.channel.send(
                            f"{message.author.mention}, You already have a proof image uploaded!"
                        )
                        await warning_msg.delete(delay=10)  # 경고 메시지는 5초 후 자동 삭제
                        break
                backup_message = f"----- Proof images of {message.author.mention} -----\n"
                for attachment in message.attachments:
                    backup_message += f"{attachment} \n"
                await bot.get_channel(proof_backup_channel_id).send(backup_message)
                backup_message = "--------------------------------------------------"
                await bot.get_channel(proof_backup_channel_id).send(backup_message)


@bot.event
async def on_raw_reaction_add(payload):
    # 관리자가 사용할 이모지와 그에 해당하는 역할 이름
    EMOJI_ROLE_MAP = {
        '✅': int(operating_system.getenv('PIONEER_CERT_ROLE_ID')),
        '❌': int(operating_system.getenv('PIONEER_CERT_ROLE_ID')),
    }

    proof_channel_id = int(operating_system.getenv('PROOF_CHANNEL_ID'))
    if payload.channel_id != proof_channel_id:
        return

    if str(payload.emoji) not in EMOJI_ROLE_MAP:
        return

    guild = bot.get_guild(payload.guild_id)
    channel = guild.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)

    # 리액션을 추가한 사용자가 관리자인지 확인
    exclude_role_list = list(map(int, operating_system.getenv('C2E_EXCLUDE_ROLE_LIST').split(',')))
    if any(role.id in exclude_role_list for role in payload.member.roles):
        # 메시지 작성자에게 역할 부여
        pioneer_cert_role_id = EMOJI_ROLE_MAP[str(payload.emoji)]
        pioneer_cert_role = guild.get_role(pioneer_cert_role_id)

        if pioneer_cert_role is None:
            logger.error(f"Role {pioneer_cert_role.mention} not found")
            return

        if str(payload.emoji) == '✅':
            await message.author.add_roles(pioneer_cert_role)
            logger.info(f"Assigned {pioneer_cert_role.mention} to {message.author}")
        elif str(payload.emoji) == '❌':
            await message.author.remove_roles(pioneer_cert_role)
            logger.info(f"Removed {pioneer_cert_role.mention} to {message.author}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    else:
        logger.error(f"An error occurred: {str(error)}")


bot.run(bot_token)
