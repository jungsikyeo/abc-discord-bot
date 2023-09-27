import discord
import os
import pymysql
import requests
import logging
import random
from datetime import datetime
from discord.ext import commands, tasks
from discord.ui import View, button, Select, Modal, InputText
from discord import Embed, ButtonStyle
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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


class WelcomeView(View):
    def __init__(self, db):
        super().__init__(timeout=None)
        self.db = db

    @button(label="Prizes", style=ButtonStyle.primary)
    async def button_prizes(self, button, interaction):
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
            logging.error(f'button_prizes error: {e}')
        finally:
            cursor.close()
            connection.close()

    @button(label="My Tickets", style=ButtonStyle.danger)
    async def button_my_tickets(self, button, interaction):
        user_id = str(interaction.user.id)

        connection = self.db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                select p.id, p.name, p.image, p.price, count(p.id) tickets
                from user_tickets u
                inner join products p on u.product_id = p.id
                where u.user_id = %s
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
            logging.error(f'button_my_tickets error: {e}')
        finally:
            cursor.close()
            connection.close()

    @button(label="My Tokens", style=ButtonStyle.green)
    async def button_my_tokens(self, button, interaction):
        user_id = str(interaction.user.id)

        connection = self.db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                select tokens
                from user_tokens
                where user_id = %s
            """, user_id)
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
            logging.error(f'button_my_tokens error: {e}')
        finally:
            cursor.close()
            connection.close()


class ProductSelectView(View):
    def __init__(self, db, all_products, org_interaction):
        super().__init__(timeout=view_timeout)
        self.db = db
        self.all_products = all_products
        self.org_interaction = org_interaction
        self.options = [discord.SelectOption(label=f"""{product['name']}""", value=product['name']) for product in
                        all_products]
        self.add_item(ProductSelect(self.db, self.options, self.all_products, self.org_interaction))

    async def on_timeout(self):
        await self.org_interaction.delete_original_message()


class ProductSelect(Select):
    def __init__(self, db, options, all_products, org_interaction):
        super().__init__(placeholder='Please choose a prize', min_values=1, max_values=1, options=options)
        self.db = db
        self.all_products = all_products
        self.org_interaction = org_interaction

    async def callback(self, interaction):
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

        await self.org_interaction.edit_original_message(
            embed=embed,
            view=buy_button_view
        )


class BuyButton(View):
    def __init__(self, db, product, org_interaction):
        super().__init__()
        self.db = db
        self.product = product
        self.org_interaction = org_interaction

    @button(label="Buy", style=discord.ButtonStyle.primary, custom_id="buy_button")
    async def button_buy(self, button, interaction):
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
                await self.org_interaction.edit_original_message(
                    content=description,
                    embed=None,
                    view=None
                )
                return

            cursor.execute("""
                select tokens
                from user_tokens
                where user_id = %s
            """, user_id)
            user = cursor.fetchone()

            if user:
                user_tokens = int(user['tokens'])
            else:
                user_tokens = 0

            if user_tokens < price:
                description = "```❌ 토큰이 부족합니다.\n\n❌ Not enough tokens.```"
                await self.org_interaction.edit_original_message(
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
                """, (user_id, product['id']))

                cursor.execute("""
                    update user_tokens set tokens = %s
                    where user_id = %s
                """, (user_tokens, user_id))

                description = f"✅ `{self.product['name']}` 경품에 응모하였습니다.\n\n" \
                              f"✅ You applied for the `{self.product['name']}` prize."
                embed = Embed(title="", description=description, color=0xFFFFFF)
                await self.org_interaction.edit_original_message(
                    embed=embed,
                    view=None
                )
            connection.commit()
        except Exception as e:
            description = "```❌ 경품을 응모하는 중에 문제가 발생했습니다.\n\n❌ There was a problem applying for the prize.```"
            await self.org_interaction.edit_original_message(
                content=description,
                embed=None,
                view=None
            )
            logging.error(f'buy error: {e}')
            connection.rollback()
        finally:
            cursor.close()
            connection.close()


class AddPrizeButton(View):
    def __init__(self):
        super().__init__()

    @button(label="Add Prize", style=discord.ButtonStyle.primary, custom_id="add_prize_button")
    async def button_add_prize(self, button, interaction):
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

    async def callback(self, interaction):
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
                logging.error(f'AddPrizeModal name error: Already have a prize with the same name.')
                return

            try:
                image = self.item_image.value
                response = requests.head(image)
                if response.status_code == 200 and 'image' in response.headers['Content-Type']:
                    pass
            except Exception as e:
                description = "```❌ 유효한 이미지URL을 입력해야합니다.\n\n❌ You must enter a valid image URL.```"
                await interaction.response.send_message(description, ephemeral=True)
                logging.error(f'AddPrizeModal image error: {e}')
                return

            try:
                price = int(self.item_price.value)
            except Exception as e:
                description = "```❌ 가격은 숫자로 입력해야합니다.\n\n❌ Price must be entered numerically.```"
                await interaction.response.send_message(description, ephemeral=True)
                logging.error(f'AddPrizeModal price error: {e}')
                return

            try:
                quantity = int(self.item_quantity.value)
            except Exception as e:
                description = "```❌ 가격은 숫자로 입력해야합니다.\n\n❌ Price must be entered numerically.```"
                await interaction.response.send_message(description, ephemeral=True)
                logging.error(f'AddPrizeModal quantity error: {e}')
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
            logging.error(f'AddPrizeModal db error: {e}')
        finally:
            cursor.close()
            connection.close()


bot = commands.Bot(command_prefix=command_flag, intents=discord.Intents.all())
db = Database(mysql_ip, mysql_port, mysql_id, mysql_passwd, mysql_db)


async def is_reservation_channel(ctx):
    return int(shopping_channel_id) == ctx.channel.id


@bot.command()
@commands.check(is_reservation_channel)
async def shop_start(ctx):
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
@commands.has_any_role('SF.Team')
async def add_prize(ctx):
    embed = Embed(title="Add Prize", description="🎁️ 아래 버튼으로 경품을 등록해주세요.\n\n"
                                                 "🎁️ Please register the prize using the button below.", color=0xFFFFFF)
    embed.set_footer(text="Powered by 으노아부지#2642")
    view = AddPrizeButton()
    await ctx.reply(embed=embed, view=view, mention_author=True)


@bot.command()
@commands.has_any_role('SF.Team')
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
        logging.error(f'giveaway_raffle error: {e}')
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
        logging.error(f'start_raffle db error: {e}')
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
        logging.error(f'get_products db error: {e}')
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
        logging.error(f'get_user_tickets db error: {e}')
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
            """, user_id)
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
@commands.has_any_role('SF.Team', 'SF.Guardian')
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
        logging.error(f'give_tokens error: {e}')


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Guardian')
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
        logging.error(f'remove_tokens error: {e}')


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
        """, (user_id,))
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
            """, (user_tokens, user_id,))
        else:
            before_user_tokens = 0
            user_tokens = token

            cursor.execute("""
                insert into user_tokens (user_id, tokens)
                values (%s, %s)
            """, (user_id, user_tokens,))

        connection.commit()
        result = {
            'success': 1,
            'before_user_tokens': before_user_tokens,
            'after_user_tokens': user_tokens
        }
    except Exception as e:
        logging.error(f'save_tokens error: {e}')
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
@commands.has_any_role('SF.Team')
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
        """, (user_id, product_name, ))
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
        logging.error(f'save_tokens error: {e}')
        connection.rollback()
    finally:
        cursor.close()
        connection.close()


class RPSGameView(View):
    def __init__(self, challenger, opponent, amount):
        super().__init__(timeout=10)  # 5초 동안 버튼 응답을 기다립니다.
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
        if self.time_left <= 0:
            embed = Embed(
                title='Response Timeout',
                description=f"{self.opponent.name}님이 응답 시간을 초과하셨습니다.\n\n{self.opponent.name } has exceeded its response time.",
                color=0xff0000,
            )
            await self.message.edit(embed=embed, view=None)
            self.update_timer.stop()
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
        choices = ["가위(Scissors)", "바위(Rock)", "보(Paper)"]
        author_choice = random.choice(choices)
        opponent_choice = random.choice(choices)

        # 결과 계산
        if author_choice == opponent_choice:
            result = "무승부(Draw)"
            description = f"{self.challenger.name}: {author_choice}\n{self.opponent.name}: {opponent_choice}\n\nResult: {result}\n\n"
            embed = Embed(
                title='✅ RPS Result',
                description=description,
                color=0xFFFFFF,
            )
            await interaction.channel.send(embed=embed)
        elif (author_choice == "가위(Scissors)" and opponent_choice == "보(Paper)") or (author_choice == "바위(Rock)" and opponent_choice == "가위(Scissors)") or (author_choice == "보(Paper)" and opponent_choice == "바위(Rock)"):
            result = f"{self.challenger.mention} is Winner!"
            description = f"{self.challenger.name}: {author_choice}\n{self.opponent.name}: {opponent_choice}\n\nResult: {result}\n\n"
            await save_rps_tokens(interaction, self.challenger, self.opponent, self.amount, description)
        else:
            result = f"{self.opponent.mention} is Winner!"
            description = f"{self.challenger.name}: {author_choice}\n{self.opponent.name}: {opponent_choice}\n\nResult: {result}\n\n"
            await save_rps_tokens(interaction, self.opponent, self.challenger, self.amount, description)

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
            description=f"❌ {self.opponent.name}님이 게임을 거부하셨습니다.\n\n❌ {self.opponent.name } rejected the game.",
            color=0xff0000,
        )
        await interaction.channel.send(embed=embed)
        self.stop()  # View를 중지하고 버튼을 비활성화


class RPSGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_played_date = {}  # user_id를 키로 하고 마지막으로 게임을 한 날짜를 값으로 가지는 딕셔너리

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
                            f"❌ You can only have a maximum of 30 tokens.",
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

            game_view = RPSGameView(ctx.author, opponent, amount)
            await game_view.send_initial_message(ctx)

            if ctx.channel.id != int(gameroom_channel_id):
                self.last_played_date[ctx.author.id] = datetime.utcnow().date()
        except Exception as e:
            logging.error(f'rps error: {e}')
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
        logging.error(f'save_rps_tokens error: {e}')


bot.add_cog(RPSGame(bot))
bot.run(bot_token)
