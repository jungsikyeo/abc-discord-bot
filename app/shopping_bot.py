import discord
import os
import pymysql
import requests
import logging
import random
import asyncio
from datetime import datetime
from discord.ext import commands
from discord.ui import View, button, Select, Modal, InputText
from discord import Embed, ButtonStyle
from discord.commands.context import ApplicationContext
from discord.commands import Option
from discord.interactions import Interaction
from dotenv import load_dotenv
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB
from prettyprinter import pprint

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
        logging.FileHandler(filename=f"{bot_log_folder}/shopping_bot.log", mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

view_timeout = 5 * 60


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


# Shopping-pi

class WelcomeView(View):
    def __init__(self, db):
        super().__init__(timeout=None)
        self.db = db

    @button(label="Prizes", style=ButtonStyle.primary)
    async def button_prizes(self, _, interaction: Interaction):
        connection = self.db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                select id, name, image, price, quantity
                from products
                where product_status = 'OPEN'
            """)
            all_products = cursor.fetchall()
            if not all_products:
                description = "```ℹ️ 응모 가능한 경품이 없습니다.\n\nℹ️ There are no prizes available.```"
                await interaction.response.send_message(description, ephemeral=True)
                return

            await interaction.response.send_message(
                view=ProductSelectView(self.db, all_products, interaction),
                ephemeral=True
            )
        except Exception as e:
            description = "```❌ 경품을 불러오는 중에 문제가 발생했습니다.\n\n❌ There was a problem while trying to retrieve the prize.```"
            await interaction.response.send_message(description, ephemeral=True)
            logger.error(f'button_prizes error: {e}')
        finally:
            cursor.close()
            connection.close()

    @button(label="My Tickets", style=ButtonStyle.danger)
    async def button_my_tickets(self, _, interaction: Interaction):
        user_id = str(interaction.user.id)

        connection = self.db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                select p.id, p.name, p.image, p.price, count(p.id) tickets
                from user_tickets u
                inner join products p on u.product_id = p.id
                where u.user_id = %s
                and p.product_status = 'OPEN'
                group by p.id, p.name, p.image, p.price
            """, user_id)
            all_user_tickets = cursor.fetchall()
            if not all_user_tickets:
                description = "```ℹ️ 응모한 티켓이 없습니다.\n\nℹ️ There is no ticket you applied for.```"
                await interaction.response.send_message(description, ephemeral=True)
                return

            description = "My tickets:\n\n"
            for user_ticket in all_user_tickets:
                description += f"""`{user_ticket['name']}`     x{user_ticket['tickets']}\n"""
            embed = Embed(title="", description=description, color=0xFFFFFF)
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
        except Exception as e:
            description = "```❌ 응모한 티켓을 불러오는 중에 문제가 발생했습니다.\n\n" \
                          "❌ There was a problem loading the ticket you applied for.```"
            await interaction.response.send_message(description, ephemeral=True)
            logger.error(f'button_my_tickets error: {e}')
        finally:
            cursor.close()
            connection.close()

    @button(label="My Tokens", style=ButtonStyle.green)
    async def button_my_tokens(self, _, interaction: Interaction):
        user_id = str(interaction.user.id)

        connection = self.db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                select tokens
                from user_tokens
                where user_id = %s
            """, str(user_id))
            user = cursor.fetchone()
            if not user:
                user_tokens = 0
            else:
                user_tokens = user['tokens']
            description = "My tokens:\n\n" \
                          f"`{user_tokens}` tokens"
            embed = Embed(title="", description=description, color=0xFFFFFF)
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
        except Exception as e:
            description = "```❌ 데이터 불러오는 중에 문제가 발생했습니다.\n\n❌ There was a problem loading data.```"
            await interaction.response.send_message(description, ephemeral=True)
            logger.error(f'button_my_tokens error: {e}')
        finally:
            cursor.close()
            connection.close()


class ProductSelectView(View):
    def __init__(self, db, all_products, org_interaction: Interaction):
        super().__init__(timeout=view_timeout)
        self.db = db
        self.all_products = all_products
        self.org_interaction = org_interaction
        self.options = [discord.SelectOption(label=f"""{product['name']}""", value=product['name']) for product in
                        all_products]
        self.add_item(ProductSelect(self.db, self.options, self.all_products, self.org_interaction))

    async def on_timeout(self):
        if self.org_interaction:
            await self.org_interaction.delete_original_response()


class ProductSelect(Select):
    def __init__(self, db, options, all_products, org_interaction: Interaction):
        super().__init__(placeholder='Please choose a prize', min_values=1, max_values=1, options=options)
        self.db = db
        self.all_products = all_products
        self.org_interaction = org_interaction

    async def callback(self, interaction: Interaction):
        selected_product = None

        for product in self.all_products:
            if product['name'] == self.values[0]:
                selected_product = product
                break

        buy_button_view = BuyButton(self.db, selected_product, interaction)

        description = "응모하시려면 아래에 `Buy` 버튼을 눌러주세요.\n\nPlease press the `Buy` button below to apply."
        embed = Embed(title=selected_product['name'], description=description, color=0xFFFFFF)
        embed.add_field(name="Price", value=f"```{selected_product['price']} tokens```", inline=True)
        embed.add_field(name="Total Quantity", value=f"```{selected_product['quantity']}```", inline=True)
        embed.set_image(url=selected_product['image'])

        await interaction.response.defer(ephemeral=True)

        await self.org_interaction.edit_original_response(
            embed=embed,
            view=buy_button_view
        )


class BuyButton(View):
    def __init__(self, db, product, org_interaction: Interaction):
        super().__init__()
        self.db = db
        self.product = product
        self.org_interaction = org_interaction

    @button(label="Buy", style=discord.ButtonStyle.primary, custom_id="buy_button")
    async def button_buy(self, _, interaction: Interaction):
        user_id = str(interaction.user.id)
        connection = self.db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                select id, name, image, price, quantity 
                from products
                where id = %s
            """, self.product['id'])
            product = cursor.fetchone()

            if product:
                price = int(product['price'])
            else:
                description = "```❌ 경품을 응모하는 중에 문제가 발생했습니다.\n\n❌ There was a problem applying for the prize.```"
                await self.org_interaction.edit_original_response(
                    content=description,
                    embed=None,
                    view=None
                )
                return

            cursor.execute("""
                select tokens
                from user_tokens
                where user_id = %s
            """, str(user_id))
            user = cursor.fetchone()

            if user:
                user_tokens = int(user['tokens'])
            else:
                user_tokens = 0

            if user_tokens < price:
                description = "```❌ 토큰이 부족합니다.\n\n❌ Not enough tokens.```"
                await self.org_interaction.edit_original_response(
                    content=description,
                    embed=None,
                    view=None
                )
                return
            else:
                user_tokens -= price

                cursor.execute("""
                    insert into user_tickets(user_id, product_id)
                    values (%s, %s)
                """, (str(user_id), product['id']))

                cursor.execute("""
                    update user_tokens set tokens = %s
                    where user_id = %s
                """, (user_tokens, str(user_id)))

                description = f"✅ `{self.product['name']}` 경품에 응모하였습니다.\n\n" \
                              f"✅ You applied for the `{self.product['name']}` prize."
                embed = Embed(title="", description=description, color=0xFFFFFF)
                await self.org_interaction.edit_original_response(
                    embed=embed,
                    view=None
                )
            connection.commit()
        except Exception as e:
            description = "```❌ 경품을 응모하는 중에 문제가 발생했습니다.\n\n❌ There was a problem applying for the prize.```"
            await self.org_interaction.edit_original_response(
                content=description,
                embed=None,
                view=None
            )
            logger.error(f'buy error: {e}')
            connection.rollback()
        finally:
            cursor.close()
            connection.close()


class AddPrizeButton(View):
    def __init__(self):
        super().__init__()

    @button(label="Add Prize", style=discord.ButtonStyle.primary, custom_id="add_prize_button")
    async def button_add_prize(self, _, interaction: Interaction):
        await interaction.response.send_modal(modal=AddPrizeModal(db))


class AddPrizeModal(Modal):
    def __init__(self, db):
        super().__init__(title="Add Prize")
        self.item_name = InputText(label="Prize Name",
                                   placeholder="Example Prize",
                                   custom_id="name",
                                   max_length=50, )
        self.item_image = InputText(label="Image URL",
                                    placeholder="https://example.com/image.jpg",
                                    custom_id="image", )
        self.item_price = InputText(label="Price",
                                    placeholder="100",
                                    custom_id="price", )
        self.item_quantity = InputText(label="Quantity",
                                       placeholder="1",
                                       custom_id="quantity", )
        self.add_item(self.item_name)
        self.add_item(self.item_image)
        self.add_item(self.item_price)
        self.add_item(self.item_quantity)
        self.db = db

    async def callback(self, interaction: Interaction):
        connection = self.db.get_connection()
        cursor = connection.cursor()

        try:
            name = self.item_name.value
            cursor.execute("""
                select count(id) cnt
                from products
                where name = %s
                and product_status = 'OPEN'
            """, name)
            item = cursor.fetchone()
            if int(item['cnt']) > 0:
                description = "```❌ 이미 동일한 이름의 경품이 있습니다.\n\n❌ You already have a prize with the same name.```"
                await interaction.response.send_message(description, ephemeral=True)
                logger.error(f'AddPrizeModal name error: Already have a prize with the same name.')
                return

            try:
                image = self.item_image.value
                response = requests.head(image)
                if response.status_code == 200 and 'image' in response.headers['Content-Type']:
                    pass
            except Exception as e:
                description = "```❌ 유효한 이미지URL을 입력해야합니다.\n\n❌ You must enter a valid image URL.```"
                await interaction.response.send_message(description, ephemeral=True)
                logger.error(f'AddPrizeModal image error: {e}')
                return

            try:
                price = int(self.item_price.value)
            except Exception as e:
                description = "```❌ 가격은 숫자로 입력해야합니다.\n\n❌ Price must be entered numerically.```"
                await interaction.response.send_message(description, ephemeral=True)
                logger.error(f'AddPrizeModal price error: {e}')
                return

            try:
                quantity = int(self.item_quantity.value)
            except Exception as e:
                description = "```❌ 가격은 숫자로 입력해야합니다.\n\n❌ Price must be entered numerically.```"
                await interaction.response.send_message(description, ephemeral=True)
                logger.error(f'AddPrizeModal quantity error: {e}')
                return

            cursor.execute("""
                insert into products (name, image, price, quantity)
                values (%s, %s, %s, %s)
            """, (name, image, price, quantity))
            description = f"✅ `{name}`이 경품으로 등록되었습니다.\n\n✅ `{name}` has been registered as a prize."
            embed = Embed(title="", description=description, color=0xFFFFFF)
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            connection.commit()
        except Exception as e:
            connection.rollback()
            description = "```❌ 데이터 처리 중에 문제가 발생했습니다.\n\n❌ There was a problem processing the data.```"
            await interaction.response.send_message(description, ephemeral=True)
            logger.error(f'AddPrizeModal db error: {e}')
        finally:
            cursor.close()
            connection.close()


bot = commands.Bot(command_prefix=command_flag, intents=discord.Intents.all())
db = Database(mysql_ip, mysql_port, mysql_id, mysql_passwd, mysql_db)


async def is_reservation_channel(ctx):
    return int(shopping_channel_id) == ctx.channel.id


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def open_shop(ctx):
    description = "ShoppingFi에 오신 것을 환영합니다!\n\n" \
                  "SearchFi가 준비한 경품 추첨에 SearchFi 토큰으로 참여할 수 있습니다.\n\n" \
                  "`Prizes` 버튼을 클릭하면 경품이 표시됩니다.\n\n" \
                  "`My Tickets` 버튼을 클릭하면 내가 참여한 경품을 확인할 수 있습니다.\n\n\n" \
                  "Welcome to ShoppingFi!\n\n" \
                  "You can participate in the raffle of prizes prepared by SearchFi with your SearchFi Token.\n\n" \
                  "Click on the `Prizes` button to see the prize.\n\n" \
                  "Click the `My Tickets` button to check out the prizes I participated in."

    embed = Embed(title="🎁 SearchFi Shop 🎁", description=description, color=0xFFFFFF)
    embed.set_image(
        url="https://media.discordapp.net/attachments/1069466892101746740/1148837901422035006/3c914e942de4d39a.gif?width=1920&height=1080")
    embed.set_footer(text="Powered by 으노아부지#2642")
    view = WelcomeView(db)
    await ctx.send(embed=embed, view=view)


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def add_prize(ctx):
    embed = Embed(title="Add Prize", description="🎁️ 아래 버튼으로 경품을 등록해주세요.\n\n"
                                                 "🎁️ Please register the prize using the button below.", color=0xFFFFFF)
    embed.set_footer(text="Powered by 으노아부지#2642")
    view = AddPrizeButton()
    await ctx.reply(embed=embed, view=view, mention_author=True)


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def giveaway_raffle(ctx):
    connection = db.get_connection()
    cursor = connection.cursor()
    try:
        result = start_raffle(db)

        description = "Congratulations! " \
                      "here is the winner list of last giveaway\n\n"
        for product, users in result.items():
            users_str = '\n'.join([f"<@{user}>" for user in users])
            description += f"🏆 `{product}` winner:\n{users_str}\n\n"

        embed = Embed(
            title='🎉 Giveaway Winner 🎉',
            description=description,
            color=0xFFFFFF,
        )

        await ctx.reply(embed=embed, mention_author=True)
    except Exception as e:
        logger.error(f'giveaway_raffle error: {e}')
        connection.rollback()
    finally:
        cursor.close()
        connection.close()


def start_raffle(db):
    connection = db.get_connection()
    cursor = connection.cursor()
    products, prizes, ticket_holders = setting_data(db)
    winners = {}
    try:
        for prize, count in prizes.items():
            already_won = set()
            weights = {user: tickets.get(prize, 0) for user, tickets in ticket_holders.items()}

            for _ in range(count):
                weights = {user: weight for user, weight in weights.items() if user not in already_won}

                if sum(weights.values()) == 0:
                    print(f"No tickets for {prize}. Skipping...")
                    continue

                winner = pick_winner(weights)
                winners.setdefault(prize, []).append(winner)
                already_won.add(winner)
        pprint(winners)

        cursor.execute("""
            update products set product_status = %s
            where product_status = 'OPEN'
        """, 'CLOSE')
        connection.commit()
    except Exception as e:
        connection.rollback()
        logger.error(f'start_raffle db error: {e}')
    finally:
        cursor.close()
        connection.close()
    return winners


def setting_data(db):
    products = get_products(db)
    prizes = {product.get('name'): product.get('quantity') for product in products}
    ticket_holders = get_user_tickets(db)

    return products, prizes, ticket_holders


def get_products(db):
    connection = db.get_connection()
    cursor = connection.cursor()
    products = None
    try:
        cursor.execute("""
            select p.id, p.name, p.image, p.price, p.quantity
            from products p 
            where p.product_status = 'OPEN'
        """)
        products = cursor.fetchall()
    except Exception as e:
        logger.error(f'get_products db error: {e}')
    finally:
        cursor.close()
        connection.close()

    return products


def get_user_tickets(db):
    connection = db.get_connection()
    cursor = connection.cursor()
    ticket_holders = {}
    try:
        cursor.execute("""
            select u.user_id, p.name, count(u.id) tickets
            from user_tickets u
            inner join products p on p.id = u.product_id
            where p.product_status = 'OPEN'
            group by u.user_id, p.id, p.name 
        """)
        user_tickets = cursor.fetchall()

        for ticket in user_tickets:
            user_id = ticket.get('user_id')
            name = ticket.get('name')
            tickets = ticket.get('tickets')

            if user_id not in ticket_holders:
                ticket_holders[user_id] = {}

            ticket_holders[user_id][name] = tickets
    except Exception as e:
        logger.error(f'get_user_tickets db error: {e}')
    finally:
        cursor.close()
        connection.close()

    return ticket_holders


def pick_winner(weights):
    total = sum(weights.values())
    rand_val = random.randint(1, total)
    current = 0

    for user, weight in weights.items():
        current += weight
        if rand_val <= current:
            return user


@bot.command()
async def giveaway_check(ctx, user_tag):
    connection = db.get_connection()
    cursor = connection.cursor()
    try:
        user_id = user_tag[2:-1]

        cursor.execute("""
            select p.id, p.name, p.image, p.price, count(p.id) tickets
            from user_tickets u
            inner join products p on u.product_id = p.id
            where u.user_id = %s
            and p.product_status = 'OPEN'
            group by p.id, p.name, p.image, p.price
        """, user_id)
        all_user_tickets = cursor.fetchall()

        cursor.execute("""
                select tokens
                from user_tokens
                where user_id = %s
            """, str(user_id))
        user = cursor.fetchone()
        if not user:
            user_tokens = 0
        else:
            user_tokens = user['tokens']

        description = f"{user_tag} tickets:\n\n"
        for user_ticket in all_user_tickets:
            description += f"""`{user_ticket['name']}`     x{user_ticket['tickets']}\n"""
        if not all_user_tickets:
            description += "No ticket.\n"

        description += f"\n" \
                       f"{user_tag} tokens:\n\n" \
                       f"""`{user_tokens}` tokens"""

        embed = Embed(title="Giveaway Check", description=description)
        await ctx.reply(embed=embed, mention_author=True)
    except Exception as e:
        print("Error:", e)
        return


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def give_tokens(ctx, user_tag, amount):
    try:
        params = {
            'user_id': user_tag[2:-1],
            'token': int(amount),
        }

        result = await save_tokens(params)

        if result.get('success') > 0:
            description = f"Successfully gave `{params.get('token')}` tokens to {user_tag}\n\n" \
                          f"{user_tag} tokens: `{result.get('before_user_tokens')}` -> `{result.get('after_user_tokens')}`"
            embed = Embed(
                title='✅ Token Given',
                description=description,
                color=0xFFFFFF,
            )
            await ctx.reply(embed=embed, mention_author=True)
            channel = bot.get_channel(int(giveup_token_channel_id))
            await channel.send(embed=embed)
    except Exception as e:
        logger.error(f'give_tokens error: {e}')


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def remove_tokens(ctx, user_tag, amount):
    try:
        params = {
            'user_id': user_tag[2:-1],
            'token': int(amount) * (-1),
        }

        result = await save_tokens(params)

        if result.get('success') > 0:
            description = f"Successfully removed `{params.get('token')}` tokens to {user_tag}\n\n" \
                          f"{user_tag} tokens: `{result.get('before_user_tokens')}` -> `{result.get('after_user_tokens')}`"
            embed = Embed(
                title='✅ Token Removed',
                description=description,
                color=0xFFFFFF,
            )
            await ctx.reply(embed=embed, mention_author=True)
            channel = bot.get_channel(int(giveup_token_channel_id))
            await channel.send(embed=embed)
    except Exception as e:
        logger.error(f'remove_tokens error: {e}')


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


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def remove_ticket(ctx, user_tag, *, product_name):
    connection = db.get_connection()
    cursor = connection.cursor()
    try:
        user_id = user_tag[2:-1]

        cursor.execute("""
            select count(1) cnt, max(a.id) as user_ticket_id
            from user_tickets a
            inner join products p on a.product_id = p.id
            where p.product_status = 'OPEN'
            and a.user_id = %s
            and upper(replace(p.name,' ', '')) = upper(replace(%s, ' ', '')) 
        """, (user_id, product_name,))
        user_ticket = cursor.fetchone()

        before_user_tickets = int(user_ticket.get('cnt'))
        if before_user_tickets > 0:
            user_ticket_id = int(user_ticket.get('user_ticket_id'))
            cursor.execute("""
                delete from user_tickets
                where id = %s
            """, (user_ticket_id,))
            connection.commit()
            after_user_tickets = before_user_tickets - 1
        else:
            after_user_tickets = 0

        description = f"Successfully removed `{product_name}` ticket to {user_tag}\n\n" \
                      f"{user_tag} `{product_name}` tickets: `{before_user_tickets}` -> `{after_user_tickets}`"
        embed = Embed(
            title='✅ Ticket Removed',
            description=description,
            color=0xFFFFFF,
        )
        await ctx.reply(embed=embed, mention_author=True)
    except Exception as e:
        logger.error(f'save_tokens error: {e}')
        connection.rollback()
    finally:
        cursor.close()
        connection.close()


@bot.slash_command(
    name="open_shop",
    description="shopping-fi shop main",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def open_shop(ctx: ApplicationContext):
    description = "ShoppingFi에 오신 것을 환영합니다!\n\n" \
                  "SearchFi가 준비한 경품 추첨에 SearchFi 토큰으로 참여할 수 있습니다.\n\n" \
                  "`Prizes` 버튼을 클릭하면 경품이 표시됩니다.\n\n" \
                  "`My Tickets` 버튼을 클릭하면 내가 참여한 경품을 확인할 수 있습니다.\n\n\n" \
                  "Welcome to ShoppingFi!\n\n" \
                  "You can participate in the raffle of prizes prepared by SearchFi with your SearchFi Token.\n\n" \
                  "Click on the `Prizes` button to see the prize.\n\n" \
                  "Click the `My Tickets` button to check out the prizes I participated in."

    embed = Embed(title="🎁 SearchFi Shop 🎁", description=description, color=0xFFFFFF)
    embed.set_image(
        url="https://media.discordapp.net/attachments/1069466892101746740/1148837901422035006/3c914e942de4d39a.gif"
            "?width=1920&height=1080")
    embed.set_footer(text="Powered by 으노아부지#2642")
    view = WelcomeView(db)
    await ctx.respond(embed=embed, view=view, ephemeral=False)


@bot.slash_command(
    name="add_prize",
    description="prize registration",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def add_prize(ctx: ApplicationContext):
    embed = Embed(title="Add Prize", description="🎁️ 아래 버튼으로 경품을 등록해주세요.\n\n"
                                                 "🎁️ Please register the prize using the button below.", color=0xFFFFFF)
    embed.set_footer(text="Powered by 으노아부지#2642")
    view = AddPrizeButton()
    await ctx.respond(embed=embed, view=view, ephemeral=True)


@bot.slash_command(
    name="giveaway_raffle",
    description="draw prizes with tickets purchased by users",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def giveaway_raffle(ctx: ApplicationContext):
    connection = db.get_connection()
    cursor = connection.cursor()
    try:
        result = start_raffle(db)

        description = "Congratulations! " \
                      "here is the winner list of last giveaway\n\n"
        for product, users in result.items():
            users_str = '\n'.join([f"<@{user}>" for user in users])
            description += f"🏆 `{product}` winner:\n{users_str}\n\n"

        embed = Embed(
            title='🎉 Giveaway Winner 🎉',
            description=description,
            color=0xFFFFFF,
        )

        await ctx.respond(embed=embed, ephemeral=False)
    except Exception as e:
        logger.error(f'giveaway_raffle error: {e}')
        connection.rollback()
    finally:
        cursor.close()
        connection.close()


@bot.slash_command(
    name="giveaway_check",
    description="check the user's tokens and tickets purchased",
    guild_ids=guild_ids
)
async def giveaway_check(ctx: ApplicationContext,
                         target_user: Option(discord.Member, "target user tag", required=True)):
    connection = db.get_connection()
    cursor = connection.cursor()
    try:
        user_id = target_user.id

        cursor.execute("""
            select p.id, p.name, p.image, p.price, count(p.id) tickets
            from user_tickets u
            inner join products p on u.product_id = p.id
            where u.user_id = %s
            and p.product_status = 'OPEN'
            group by p.id, p.name, p.image, p.price
        """, user_id)
        all_user_tickets = cursor.fetchall()

        cursor.execute("""
                select tokens
                from user_tokens
                where user_id = %s
            """, str(user_id))
        user = cursor.fetchone()
        if not user:
            user_tokens = 0
        else:
            user_tokens = user['tokens']

        description = f"{target_user} tickets:\n\n"
        for user_ticket in all_user_tickets:
            description += f"""`{user_ticket['name']}`     x{user_ticket['tickets']}\n"""
        if not all_user_tickets:
            description += "No ticket.\n"

        description += f"\n" \
                       f"{target_user} tokens:\n\n" \
                       f"""`{user_tokens}` tokens"""

        embed = Embed(title="Giveaway Check", description=description)
        await ctx.respond(embed=embed, ephemeral=False)
    except Exception as e:
        print("Error:", e)
        return


@bot.slash_command(
    name="give_tokens",
    description="check the user's tokens and tickets purchased",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def give_tokens(ctx: ApplicationContext,
                      target_user: Option(discord.Member, "target user tag", required=True),
                      quantity: Option(int, "token quantity", required=True)):
    try:
        params = {
            'user_id': target_user.id,
            'token': int(quantity),
        }

        result = await save_tokens(params)

        if result.get('success') > 0:
            description = f"Successfully gave `{params.get('token')}` tokens to {target_user}\n\n" \
                          f"{target_user} tokens: `{result.get('before_user_tokens')}` -> `{result.get('after_user_tokens')}`"
            embed = Embed(
                title='✅ Token Given',
                description=description,
                color=0xFFFFFF,
            )
            await ctx.respond(embed=embed, ephemeral=False)
            channel = bot.get_channel(int(giveup_token_channel_id))
            await channel.send(embed=embed)
    except Exception as e:
        logger.error(f'give_tokens error: {e}')


@bot.slash_command(
    name="remove_tokens",
    description="check the user's tokens and tickets purchased",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def remove_tokens(ctx: ApplicationContext,
                        target_user: Option(discord.Member, "target user tag", required=True),
                        quantity: Option(int, "token quantity", required=True)):
    try:
        params = {
            'user_id': target_user.id,
            'token': int(quantity) * (-1),
        }

        result = await save_tokens(params)

        if result.get('success') > 0:
            description = f"Successfully removed `{params.get('token')}` tokens to {target_user}\n\n" \
                          f"{target_user} tokens: `{result.get('before_user_tokens')}` -> `{result.get('after_user_tokens')}`"
            embed = Embed(
                title='✅ Token Removed',
                description=description,
                color=0xFFFFFF,
            )
            await ctx.respond(embed=embed, ephemeral=False)
            channel = bot.get_channel(int(giveup_token_channel_id))
            await channel.send(embed=embed)
    except Exception as e:
        logger.error(f'remove_tokens error: {e}')


@bot.slash_command(
    name="remove_ticket",
    description="remove tickets purchased by users",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def remove_ticket(ctx: ApplicationContext,
                        target_user: Option(discord.Member, "target user tag", required=True),
                        prize_name: Option(str, "name of the prize to be deleted", required=True)):
    connection = db.get_connection()
    cursor = connection.cursor()
    try:
        user_id = target_user.id

        cursor.execute("""
            select count(1) cnt, max(a.id) as user_ticket_id
            from user_tickets a
            inner join products p on a.product_id = p.id
            where p.product_status = 'OPEN'
            and a.user_id = %s
            and upper(replace(p.name,' ', '')) = upper(replace(%s, ' ', '')) 
        """, (user_id, prize_name,))
        user_ticket = cursor.fetchone()

        before_user_tickets = int(user_ticket.get('cnt'))
        if before_user_tickets > 0:
            user_ticket_id = int(user_ticket.get('user_ticket_id'))
            cursor.execute("""
                delete from user_tickets
                where id = %s
            """, (user_ticket_id,))
            connection.commit()
            after_user_tickets = before_user_tickets - 1
        else:
            after_user_tickets = 0

        description = f"Successfully removed `{prize_name}` ticket to {target_user}\n\n" \
                      f"{target_user} `{prize_name}` tickets: `{before_user_tickets}` -> `{after_user_tickets}`"
        embed = Embed(
            title='✅ Ticket Removed',
            description=description,
            color=0xFFFFFF,
        )
        await ctx.respond(embed=embed, ephemeral=False)
    except Exception as e:
        logger.error(f'save_tokens error: {e}')
        connection.rollback()
    finally:
        cursor.close()
        connection.close()


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    else:
        logger.error(f"An error occurred: {str(error)}")


# -----------------------------------------------
# Bidding-pi

class MarketCreateView(View):
    def __init__(self, db, markets):
        super().__init__(timeout=view_timeout)
        self.db = db
        self.markets = markets
        self.options = [
            discord.SelectOption(
                label=f"{market_data['name']} ({market_data['start_time']} ~ {market_data['end_time']})",
                value=str(market_data['id'])) for market_data in markets.values()
        ]
        if len(self.options) > 0:
            self.add_item(MarketSelect(self.db, self.markets, self.options))

    @button(label='New Market', style=ButtonStyle.green)
    async def new_market(self, _, interaction):
        market = {
            'id': None,
            'name': '',
            'description': '',
            'start_time': '',
            'end_time': ''
        }
        await interaction.response.send_modal(MarketModal(self.db, market, interaction))


class MarketSelect(Select):
    def __init__(self, db, markets, options):
        super().__init__(placeholder='Please choose a market', min_values=1, max_values=1, options=options)
        self.db = db
        self.markets = markets

    async def callback(self, interaction: Interaction):
        market_id = int(self.values[0])
        market = self.markets[market_id]
        await interaction.response.send_modal(MarketModal(self.db, market, interaction))


class MarketModal(Modal):
    def __init__(self, db, market, org_interaction):
        super().__init__(title="Create Market")
        self.db = db
        self.org_interaction = org_interaction
        self.market_id = market.get('id')
        self.market_name = InputText(label="Market Name",
                                     value=market.get('name'),
                                     placeholder='Enter Market Name',
                                     min_length=1,
                                     max_length=100)
        self.market_description = InputText(label="Market Description",
                                            value=market.get('description'),
                                            placeholder='Enter Market Description',
                                            min_length=1,
                                            max_length=1000)

        self.start_time = InputText(label="Start Time",
                                    value=market.get('start_time'),
                                    placeholder='Enter Start Time (yyyy-mm-dd hh24:mi)')

        self.end_time = InputText(label="End Time",
                                  value=market.get('end_time'),
                                  placeholder='Enter End Time (yyyy-mm-dd hh24:mi)')

        self.add_item(self.market_name)
        self.add_item(self.market_description)
        self.add_item(self.start_time)
        self.add_item(self.end_time)

    async def callback(self, interaction: Interaction):
        try:
            datetime.strptime(self.start_time.value, '%Y-%m-%d %H:%M')
            datetime.strptime(self.end_time.value, '%Y-%m-%d %H:%M')
        except ValueError as e:
            description = "```❌ 날짜 형식이 잘못되었습니다.\nyyyy-mm-dd hh24:mi 형식을 사용하십시오.\n\n" \
                          "❌ Invalid date format.\nPlease use yyyy-mm-dd hh24:mi format.```"
            await interaction.response.send_message(description, ephemeral=True)
            logger.error(f'MarketModal datetime error: {e}')
            return

        connection = self.db.get_connection()
        cursor = connection.cursor()

        market_id = self.market_id
        market_name = self.market_name.value
        market_description = self.market_description.value
        market_start_time = self.start_time.value
        market_end_time = self.end_time.value

        try:
            if self.market_id:
                cursor.execute("""
                    update auction_markets set 
                        name = %s, 
                        description = %s, 
                        start_time = %s, 
                        end_time = %s
                    where id = %s
                """, (market_name,
                      market_description,
                      market_start_time,
                      market_end_time,
                      market_id))
            else:
                cursor.execute("""
                    insert into auction_markets(name, description, start_time, end_time)
                    values (%s, %s, %s, %s)
                """, (market_name, market_description, market_start_time, market_end_time))

            connection.commit()

            await interaction.response.defer(ephemeral=True)

            if self.org_interaction:
                embed = Embed(
                    title="Create Market Complete",
                    description="✅ 옥션 마켓이 성공적으로 등록되었습니다! 아래 명령어로 경품을 등록해주세요.\n"
                                "`!add_auction_prize`\n\n"
                                "✅ Auction Market registered successfully! "
                                "Please register the prize using the command below.\n"
                                "`!add_auction_prize`",
                )
                await self.org_interaction.edit_original_response(
                    embed=embed,
                    view=None
                )
        except Exception as e:
            connection.rollback()
            description = "```❌ 데이터 처리 중에 문제가 발생했습니다.\n\n❌ There was a problem processing the data.```"
            await interaction.response.send_message(description, ephemeral=True)
            logger.error(f'MarketModal db error: {e}')
        finally:
            cursor.close()
            connection.close()


class AuctionPrizeAddView(View):
    def __init__(self, db, markets):
        super().__init__(timeout=view_timeout)
        self.db = db

        # 마켓 선택을 위한 콤보박스 생성
        self.options = [
            discord.SelectOption(
                label=f"{market_data['name']} ({market_data['start_time']} ~ {market_data['end_time']})",
                value=str(market_data['id'])) for market_data in markets.values()
        ]
        if len(self.options) > 0:
            self.add_item(AuctionPrizeAddSelect(self.db, self.options))


class AuctionPrizeAddSelect(Select):
    def __init__(self, db, options):
        super().__init__(placeholder='Please choose a market', min_values=1, max_values=1, options=options)
        self.db = db

    async def callback(self, interaction: Interaction):
        await interaction.response.send_modal(AuctionPrizeAddModal(self.db, self.values[0]))


class AuctionPrizeAddModal(Modal):
    def __init__(self, db, market_id):
        super().__init__(title="Add Prize")
        self.db = db
        self.market_id = int(market_id)
        self.prize_name = InputText(label="Prize Name",
                                    placeholder="Enter the name of the prize",
                                    min_length=1,
                                    max_length=100)
        self.winners = InputText(label="Winners",
                                 placeholder="Enter the number of winners of the prize", )
        self.min_bid = InputText(label="Minimum Bidding Price",
                                 placeholder="Enter minimum bidding price")
        self.add_item(self.prize_name)
        self.add_item(self.winners)
        self.add_item(self.min_bid)

    async def callback(self, interaction):
        connection = self.db.get_connection()
        cursor = connection.cursor()

        market_id = self.market_id
        prize_name = self.prize_name.value
        prize_winners = self.winners.value
        prize_min_bid = self.min_bid.value

        try:
            cursor.execute("""
                insert into auction_prizes(market_id, name, winners, min_bid)
                values (%s, %s, %s, %s)
            """, (market_id, prize_name, prize_winners, prize_min_bid))

            connection.commit()

            embed = Embed(
                title="Add Prize Complete",
                description="✅ 경품이 성공적으로 추가되었습니다! 아래 명령어로 옥션 마켓을 오픈하세요.\n"
                            "`!open_market`\n\n"
                            "✅ Prize has been successfully added! "
                            "Open the auction market using the command below.\n"
                            "`!open_market`"
            )
            await interaction.response.send_message(embed=embed)
        except Exception as e:
            connection.rollback()
            description = "```❌ 데이터 처리 중에 문제가 발생했습니다.\n\n❌ There was a problem processing the data.```"
            await interaction.response.send_message(description, ephemeral=True)
            logger.error(f'AuctionPrizeAddModal db error: {e}')
        finally:
            cursor.close()
            connection.close()


class OpenMarketView(View):
    def __init__(self, db, markets, prizes):
        super().__init__()
        self.db = db
        self.markets = markets
        self.prizes = prizes

        # 마켓 선택을 위한 콤보박스 생성
        self.options = [
            discord.SelectOption(
                label=f"{market_data['name']} ({market_data['start_time']} ~ {market_data['end_time']})",
                value=str(market_data['id'])) for market_data in markets.values()
        ]
        if len(self.options) > 0:
            self.add_item(OpenMarketSelect(self.db, self.markets, self.prizes, self.options))


class OpenMarketSelect(Select):
    def __init__(self, db, markets, prizes, options):
        super().__init__(placeholder='Please choose a auction market', min_values=1, max_values=1, options=options)
        self.db = db
        self.markets = markets
        self.prizes = prizes

    async def callback(self, interaction: Interaction):
        market_id = int(self.values[0])
        market = self.markets[market_id]

        # 지정된 날짜와 시간
        date_format = "%Y-%m-%d %H:%M"

        # 날짜와 시간을 datetime 객체로 변환
        start_dt = datetime.strptime(market['start_time'], date_format)
        end_dt = datetime.strptime(market['end_time'], date_format)

        # 유닉스 타임스탬프로 변환 (초 단위)
        start_timestamp = int(start_dt.timestamp())
        end_timestamp = int(end_dt.timestamp())

        embed = Embed(title=market['name'], description=market['description'])
        embed.add_field(name="START TIME", value=f"<t:{start_timestamp}>", inline=True)
        embed.add_field(name="END TIME", value=f"<t:{end_timestamp}:R>", inline=True)
        embed.add_field(name="", value="----------------------------------------------------------------------",
                        inline=False)

        # 해당 마켓의 경품들을 동적으로 추가
        if market_id in self.prizes:
            for prize in self.prizes[market_id]:
                bid = get_auction_bid(self.db, market_id, prize['prize_id'])
                bid_users = ""
                if len(bid.get('bid_users', [])) > 0:
                    index = 1
                    for bid_user in bid.get('bid_users', []):
                        if index <= 2:
                            user_name = f"{bid_user['user_name'][0:1]} * * * *"
                        elif index > 10:
                            break
                        else:
                            user_name = bid_user['user_name']
                        bid_users += f"{user_name} - {bid_user['total_bid_price']} SF\n"
                        index += 1
                embed.add_field(name=f"""🎁️  {prize['name']}  -  Top {prize['winners']}  🎁️""",
                                value=f"{bid_users}"
                                      f"Min Bid: {prize['min_bid']} SF", inline=True)

        view = BidButtonView(self.db, market_id, self.prizes, end_dt, interaction)
        await interaction.response.send_message(embed=embed, view=view)


class BidButtonView(View):
    def __init__(self, db, market_id, prizes, end_time: datetime, org_interaction: Interaction):
        super().__init__()
        self.timeout = None
        self.db = db
        self.market_id = market_id
        self.prizes = prizes
        self.end_time = end_time
        self.org_interaction = org_interaction
        self.loop = asyncio.get_event_loop()
        asyncio.create_task(self.check_end_time_periodically())

    async def check_end_time_periodically(self):
        while True:
            if datetime.now() > self.end_time:
                self.children[0].disabled = True  # 첫 번째 버튼 (bid 버튼)을 비활성화합니다.
                await self.org_interaction.edit_original_response(view=self)
                await self.auction_winners()
                break  # 루프 종료
            await asyncio.sleep(1)  # 1초마다 확인

    @button(label='bid', style=ButtonStyle.green)
    async def place_bid(self, _, interaction: Interaction):
        user_id = interaction.user.id
        view = BidPrizeView(self.db, self.market_id, self.prizes, user_id, self.org_interaction)
        await interaction.response.send_message(view=view, ephemeral=True)

    async def auction_winners(self):
        for prize in self.prizes[self.market_id]:
            bid = get_auction_bid(self.db, self.market_id, prize['prize_id'])
            bid_users_sorted = sorted(bid.get('bid_users', []), key=lambda x: x['total_bid_price'], reverse=True)
            non_winners = {bid_user['user_id']: bid_user['total_bid_price'] for bid_user in bid_users_sorted}
            winners_count = 0
            winners_list = []

            while winners_count < prize['winners'] and bid_users_sorted:
                # 현재 최고 입찰 가격을 가진 사람들을 가져옴
                current_top_price = bid_users_sorted[0]['total_bid_price']
                same_price_bidders = [b for b in bid_users_sorted if b['total_bid_price'] == current_top_price]

                # 만약 동률자 수가 남은 승자 수보다 많거나 같으면 랜덤 선택
                if len(same_price_bidders) > prize['winners'] - winners_count:
                    chosen_winners = random.sample(same_price_bidders, prize['winners'] - winners_count)
                    winners_list.extend(chosen_winners)
                    winners_count += len(chosen_winners)
                else:
                    winners_list.extend(same_price_bidders)
                    winners_count += len(same_price_bidders)

                # 처리한 입찰자 제거
                bid_users_sorted = [b for b in bid_users_sorted if b['total_bid_price'] != current_top_price]

            # 당첨자 목록에서 미당첨자 제거
            for winner in winners_list:
                if winner['user_id'] in non_winners:
                    del non_winners[winner['user_id']]

            # 승자 출력
            winners_mentions = ', '.join([f"<@{winner['user_id']}>" for winner in winners_list])
            await self.org_interaction.channel.send(f"**Winners for {prize['name']} - Top {prize['winners']}** : "
                                                    f"{winners_mentions}")

            # 미당첨자 환불 처리
            for non_winner_id, total_bid_price in non_winners.items():
                deduction = int(total_bid_price * 0.20)  # 20% 차감
                refund_price = total_bid_price - deduction
                # DB에서 환불 처리
                await self.refund_user(prize['prize_id'], non_winner_id, total_bid_price, refund_price)

    async def refund_user(self, prize_id, non_winner_id, total_bid_price, refund_price):
        connection = self.db.get_connection()
        cursor = connection.cursor()
        try:
            user = bot.get_user(non_winner_id)
            if user:
                user_name = user.name
            else:
                user_name = "non_username"
            cursor.execute("""
                insert into auction_refunds(market_id, prize_id, user_id, user_name, total_bid_price, refund_price)
                values (%s, %s, %s, %s, %s, %s)
            """, (self.market_id, prize_id, non_winner_id, user_name, total_bid_price, refund_price))

            cursor.execute("""
                update user_tokens set tokens = tokens + %s
                where user_id = %s
            """, (refund_price, non_winner_id))

            connection.commit()

        except Exception as e:
            logger.error(f'BidButtonView - refund_user error: {e}')
            return
        finally:
            cursor.close()
            connection.close()


class BidPrizeView(View):
    def __init__(self, db, market_id, prizes, user_id, org_interaction: Interaction):
        super().__init__()
        self.db = db
        self.market_id = market_id
        self.prizes = prizes
        self.user_id = user_id
        self.org_interaction = org_interaction

        # 경품 선택을 위한 콤보박스 생성
        self.options = [
            discord.SelectOption(
                label=f"{prize_data['name']}",
                value=str(prize_data['prize_id'])) for prize_data in self.prizes[market_id]
        ]
        if len(self.options) > 0:
            self.add_item(BidPrizeSelect(self.db, self.market_id, self.user_id, self.options, self.org_interaction))


class BidPrizeSelect(Select):
    def __init__(self, db, market_id, user_id, options, org_interaction: Interaction):
        super().__init__(placeholder='Please choose a prize', min_values=1, max_values=1, options=options)
        self.db = db
        self.market_id = market_id
        self.user_id = user_id
        self.org_interaction = org_interaction

    async def callback(self, interaction: Interaction):
        prize_id = int(self.values[0])
        my_total_bid = get_my_auction_bid(db, self.market_id, prize_id, self.user_id)
        await interaction.response.send_modal(
            BidModal(self.db, self.market_id, prize_id, self.user_id, my_total_bid, self.org_interaction)
        )


class BidModal(Modal):
    def __init__(self, db, market_id, prize_id, user_id, my_total_bid, org_interaction: Interaction):
        super().__init__(title="Bidding")
        self.db = db
        self.market_id = market_id
        self.prize_id = prize_id
        self.user_id = user_id
        self.my_total_bid = my_total_bid
        self.bid_amount = InputText(label=f"Your current bid price: {my_total_bid} SF",
                                    placeholder='Enter additional bid amounts',
                                    min_length=1,
                                    max_length=20)
        self.add_item(self.bid_amount)
        self.org_interaction = org_interaction

    async def callback(self, interaction: Interaction):
        connection = self.db.get_connection()
        cursor = connection.cursor()

        markets = get_auction_market(self.db)
        market = markets[self.market_id]

        # 지정된 날짜와 시간
        date_format = "%Y-%m-%d %H:%M"

        # 날짜와 시간을 datetime 객체로 변환
        start_dt = datetime.strptime(market['start_time'], date_format)
        end_dt = datetime.strptime(market['end_time'], date_format)

        # 유닉스 타임스탬프로 변환 (초 단위)
        start_timestamp = int(start_dt.timestamp())
        end_timestamp = int(end_dt.timestamp())

        if datetime.now() < start_dt:
            print(datetime.now(), start_dt)
            description = "```❌ 아직 마켓이 오픈되지 않았습니다.\n\n❌ The market hasn't opened yet.```"
            await interaction.response.send_message(content=description,
                                                    embed=None,
                                                    view=None,
                                                    ephemeral=True)
            return

        if datetime.now() >= end_dt:
            print(datetime.now(), end_dt)
            description = "```❌ 마켓이 종료되어 입찰할 수 없습니다.\n\n❌ The market has closed and cannot bid.```"
            await interaction.response.send_message(content=description,
                                                    embed=None,
                                                    view=None,
                                                    ephemeral=True)
            return

        try:
            user = bot.get_user(self.user_id)
            try:
                bid_price = int(self.bid_amount.value)
            except Exception as e:
                logger.error(f'BidModal error: {e}')
                description = "```❌ 0보다 큰 정수를 입력하세요.\n\n❌ Enter an integer greater than 0.```"
                await interaction.response.send_message(content=description,
                                                        embed=None,
                                                        view=None,
                                                        ephemeral=True)
                return

            if bid_price < 0:
                description = "```❌ 0보다 큰 정수를 입력하세요.\n\n❌ Enter an integer greater than 0.```"
                await interaction.response.send_message(content=description,
                                                        embed=None,
                                                        view=None,
                                                        ephemeral=True)
                return

            cursor.execute("""
                select tokens
                from user_tokens
                where user_id = %s
            """, self.user_id)
            user_token_db = cursor.fetchone()
            if not user:
                user_tokens = 0
            else:
                user_tokens = user_token_db['tokens']

            prize = get_auction_prize(db, self.prize_id)

            if user_tokens < bid_price:
                description = "```❌ 토큰이 부족합니다.\n\n❌ Not enough tokens.```"
                await interaction.response.send_message(content=description,
                                                        embed=None,
                                                        view=None,
                                                        ephemeral=True)
                return
            elif int(prize['min_bid']) > (self.my_total_bid + bid_price):
                description = "```❌ 최소 입찰 가격 이상을 입력해주세요.\n\n❌ Please enter the minimum bid price.```"
                await interaction.response.send_message(content=description,
                                                        embed=None,
                                                        view=None,
                                                        ephemeral=True)
                return
            else:
                user_tokens -= bid_price

            cursor.execute("""
                insert into auction_bids(market_id, prize_id, user_id, user_name, bid_price)
                values (%s, %s, %s, %s, %s)
            """, (self.market_id, self.prize_id, self.user_id, user.name, bid_price))

            cursor.execute("""
                update user_tokens set tokens = %s
                where user_id = %s
            """, (user_tokens, self.user_id))

            connection.commit()

        except Exception as e:
            logger.error(f'BidModal error: {e}')
            return
        finally:
            cursor.close()
            connection.close()

        await interaction.response.defer(ephemeral=True)

        embed = Embed(title=market['name'], description=market['description'])
        embed.add_field(name="START TIME", value=f"<t:{start_timestamp}>", inline=True)
        embed.add_field(name="END TIME", value=f"<t:{end_timestamp}:R>", inline=True)
        embed.add_field(name="", value="----------------------------------------------------------------------",
                        inline=False)

        prizes = get_auction_prizes(self.db)

        # 해당 마켓의 경품들을 동적으로 추가
        if self.market_id in prizes:
            for prize in prizes[self.market_id]:
                bid = get_auction_bid(self.db, self.market_id, prize['prize_id'])
                bid_users = ""
                if len(bid.get('bid_users', [])) > 0:
                    index = 1
                    for bid_user in bid.get('bid_users', []):
                        if index <= 2:
                            user_name = f"{bid_user['user_name'][0:1]} * * * *"
                        elif index > 10:
                            break
                        else:
                            user_name = bid_user['user_name']
                        bid_users += f"{user_name} - {bid_user['total_bid_price']} SF\n"
                        index += 1
                embed.add_field(name=f"""🎁️  {prize['name']}  -  Top {prize['winners']}  🎁️""",
                                value=f"{bid_users}"
                                      f"Min Bid: {prize['min_bid']} SF", inline=True)

        view = BidButtonView(self.db, self.market_id, prizes, self.org_interaction)

        await self.org_interaction.edit_original_response(
            embed=embed,
            view=view
        )


def get_auction_market(db):
    connection = db.get_connection()
    cursor = connection.cursor()
    markets = {}
    try:
        cursor.execute("""
            select id, name, description, start_time, end_time 
            from auction_markets
            order by id
        """)
        markets_db = cursor.fetchall()
        markets = {
            market.get('id'): {
                'id': market.get('id'),
                'name': market.get('name'),
                'description': market.get('description'),
                'start_time': market.get('start_time'),
                'end_time': market.get('end_time')
            } for market in markets_db
        }
    except Exception as e:
        connection.rollback()
        logger.error(f'get_auction_market db error: {e}')
    finally:
        cursor.close()
        connection.close()
    return markets


def get_auction_prizes(db):
    connection = db.get_connection()
    cursor = connection.cursor()
    prizes = {}
    try:
        cursor.execute("""
            select id, market_id, name, winners, min_bid 
            from auction_prizes
            order by id
        """)
        prizes_db = cursor.fetchall()

        for prize in prizes_db:
            market_id = prize.get('market_id')
            if market_id not in prizes:
                prizes[market_id] = []
            prizes[market_id].append({
                'prize_id': prize.get('id'),
                'market_id': prize.get('market_id'),
                'name': prize.get('name'),
                'winners': prize.get('winners'),
                'min_bid': prize.get('min_bid')
            })
    except Exception as e:
        connection.rollback()
        logger.error(f'get_auction_prizes db error: {e}')
    finally:
        cursor.close()
        connection.close()
    return prizes


def get_auction_prize(db, prize_id):
    connection = db.get_connection()
    cursor = connection.cursor()
    prize = {}
    try:
        cursor.execute("""
            select id, market_id, name, winners, min_bid 
            from auction_prizes
            where id = %s
        """, prize_id)
        prizes_db = cursor.fetchone()

        if prizes_db:
            prize = {
                'prize_id': prizes_db.get('id'),
                'market_id': prizes_db.get('market_id'),
                'name': prizes_db.get('name'),
                'winners': prizes_db.get('winners'),
                'min_bid': prizes_db.get('min_bid')
            }
    except Exception as e:
        connection.rollback()
        logger.error(f'get_auction_prize db error: {e}')
    finally:
        cursor.close()
        connection.close()
    return prize


def get_auction_bid(db, market_id, prize_id):
    connection = db.get_connection()
    cursor = connection.cursor()
    bid = {}
    try:
        cursor.execute("""
            with market_prizes as (
                select
                    ap.market_id,
                    ap.id as prize_id,
                    ap.name as prize_name,
                    ap.winners,
                    ap.min_bid
                from auction_markets am
                inner join auction_prizes ap on am.id = ap.market_id
                where market_id = %s
            )
            select
                mp.market_id,
                mp.prize_id,
                mp.prize_name,
                mp.winners,
                mp.min_bid,
                ab.user_id,
                max(ab.user_name) as user_name,
                sum(ab.bid_price) as total_bid_price
            from market_prizes mp
            left outer join auction_bids ab on mp.market_id = ab.market_id and mp.prize_id = ab.prize_id
            where mp.prize_id = %s
            group by
                mp.market_id,
                mp.prize_id,
                mp.prize_name,
                mp.winners,
                mp.min_bid,
                ab.user_id
            order by total_bid_price desc
        """, (market_id, prize_id))
        bids_db = cursor.fetchall()

        index = 1
        for row in bids_db:
            prize_name = row.get('prize_name')
            winners = row.get('winners')
            min_bid = row.get('min_bid')
            user_id = row.get('user_id')
            user_name = row.get('user_name')
            total_bid_price = row.get('total_bid_price')

            if index == 1:
                bid = {
                    'prize_id': prize_id,
                    'prize_name': prize_name,
                    'winners': winners,
                    'min_bid': int(min_bid),
                    'bid_users': []
                }
            if user_name:
                bid['bid_users'].append({
                    'user_id': user_id,
                    'user_name': user_name,
                    'total_bid_price': int(total_bid_price)
                })
            index += 1
    except Exception as e:
        connection.rollback()
        logger.error(f'get_auction_bid db error: {e}')
    finally:
        cursor.close()
        connection.close()
    return bid


def get_my_auction_bid(db, market_id, prize_id, user_id):
    connection = db.get_connection()
    cursor = connection.cursor()
    my_total_bid = 0
    try:
        cursor.execute("""
            select 
                market_id, 
                prize_id, 
                user_id, 
                max(user_name) as user_name, 
                sum(bid_price) as total_bid_price
            from auction_bids
            where market_id = %s 
            and prize_id = %s
            and user_id = %s
            group by market_id, prize_id, user_id
        """, (market_id, prize_id, user_id))
        bid_db = cursor.fetchone()
        if bid_db:
            my_total_bid = bid_db['total_bid_price']
    except Exception as e:
        connection.rollback()
        logger.error(f'get_my_auction_bid db error: {e}')
    finally:
        cursor.close()
        connection.close()
    return my_total_bid


@bot.command()
async def create_auction(ctx):
    markets = get_auction_market(db)
    embed = Embed(title="Create Market",
                  description="버튼을 클릭하여 새로운 옥션 마켓을 생성하거나, 기존 옥션 마켓을 선택하여 수정할 수 있습니다.\n\n"
                              "You can create a new auction market by clicking the button, "
                              "or you can modify it by selecting an existing auction market.",
                  color=0xFFFFFF)
    await ctx.send(embed=embed, view=MarketCreateView(db, markets))


@bot.command()
async def add_auction_prize(ctx):
    markets = get_auction_market(db)
    embed = Embed(title="Add Prize",
                  description="옥션 마켓을 선택하고 경품을 등록해주세요.\n\n"
                              "Please select the auction market and register the prize.",
                  color=0xFFFFFF)
    await ctx.send(embed=embed,
                   view=AuctionPrizeAddView(db, markets))


@bot.command()
async def open_auction(ctx):
    markets = get_auction_market(db)
    prizes = get_auction_prizes(db)
    embed = Embed(title="Open Market",
                  description="오픈할 옥션 마켓을 선택해주세요.\n\n"
                              "Please select a auction market to open.",
                  color=0xFFFFFF)

    await ctx.send(embed=embed, view=OpenMarketView(db, markets, prizes))


bot.run(bot_token)
