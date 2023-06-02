import requests
import os
import uuid
import pymysql
import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from urllib.parse import unquote
from typing import List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

mysql_ip = os.getenv("MYSQL_IP")
mysql_port = os.getenv("MYSQL_PORT")
mysql_id = os.getenv("MYSQL_ID")
mysql_passwd = os.getenv("MYSQL_PASSWD")
mysql_db = os.getenv("MYSQL_DB")


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
    def update_count(db, count_type, project_id, dc_id):
        select_query = ""
        select_query = select_query + f"update projects set {count_type} = ifnull(nullif({count_type},0),0)+1 where id = '{project_id}' "

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                conn.commit()
                return Queries.select_count(db, count_type, project_id, dc_id)

    def select_count(db, count_type, project_id, dc_id):
        select_query = ""
        select_query = select_query + f"select {count_type} from projects where id = '{project_id}' "

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchone()
                return result

    def insert_project(db, uuid, form):
        name = form["name"]
        discordUrl = form["discordUrl"]
        twitterUrl = form["twitterUrl"]
        twitterProfileImage = form["twitterProfileImage"]
        mintDateOption = form["mintDateOption"]
        supplyOption = form["supplyOption"]
        wlPriceOption = form["wlPriceOption"]
        pubPriceOption = form["pubPriceOption"]
        blockchain = form["blockchain"]
        regUser = form["regUser"]

        try:
            if form["noUpdate"]:
                noUpdate = 1
            else:
                noUpdate = 0
        except Exception as e:
            noUpdate = 0

        if mintDateOption == 'TBA':
            mintDate = "'TBA'"
            hasTime = 'False'
        else:
            mintDate = form["mintDate"]
            mintDate = f"concat(cast(UNIX_TIMESTAMP('{mintDate}') as char),'000')"
            hasTime = 'True'

        if supplyOption == 'TBA':
            supply = "TBA"
        else:
            supply = form["supply"]

        if wlPriceOption == 'TBA':
            wlPrice = "TBA"
        else:
            wlPrice = form["wlPrice"]

        if pubPriceOption == 'TBA':
            pubPrice = "TBA"
        else:
            pubPrice = form["pubPrice"]

        check_query = f"SELECT COUNT(*) cnt FROM projects WHERE lower(twitterUrl) = lower('{twitterUrl}')"
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(check_query)
                result = cursor.fetchone()
                if int(result['cnt']) > 0:
                    return {"status": "ERROR", "msg": "Twitter URL already exists"}

        insert_query = f"""
            insert into projects
            (
                id, name, discordUrl, twitterUrl, twitterProfileImage, mintDate, 
                supply, wlPrice, pubPrice, blockchain, hasTime, 
                regUser, noUpdate, isAlphabot, lastUpdated, dateCreated
            ) 
            values 
            (
                '{uuid}', %s, '{discordUrl}', '{twitterUrl}', '{twitterProfileImage}', {mintDate}, 
                '{supply}', '{wlPrice}', '{pubPrice}', '{blockchain}', '{hasTime}', 
                '{regUser}', '{noUpdate}','N', concat(cast(UNIX_TIMESTAMP() as char),'000'), concat(cast(UNIX_TIMESTAMP() as char),'000')
            )
        """
        print(insert_query)
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(insert_query, (name,))
                    conn.commit()
            return {"status":"OK"}
        except Exception as e:
            conn.rollback()
            print(e)
            return {"status": "ERROR", "msg": e}

    def update_project(db, form):
        id = form["id"]
        name = form["name"]
        twitterUrl = form["twitterUrl"]
        twitterProfileImage = form["twitterProfileImage"]
        mintDateOption = form["mintDateOption"]
        supplyOption = form["supplyOption"]
        wlPriceOption = form["wlPriceOption"]
        pubPriceOption = form["pubPriceOption"]
        blockchain = form["blockchain"]

        try:
            if form["noUpdate"]:
                noUpdate = 1
            else:
                noUpdate = 0
        except Exception as e:
            noUpdate = 0

        if mintDateOption == 'TBA':
            mintDate = "'TBA'"
            hasTime = 'False'
        else:
            mintDate = form["mintDate"]
            mintDate = f"concat(cast(UNIX_TIMESTAMP('{mintDate}') as char),'000')"
            hasTime = 'True'

        if supplyOption == 'TBA':
            supply = "TBA"
        else:
            supply = form["supply"]

        if wlPriceOption == 'TBA':
            wlPrice = "TBA"
        else:
            wlPrice = form["wlPrice"]

        if pubPriceOption == 'TBA':
            pubPrice = "TBA"
        else:
            pubPrice = form["pubPrice"]

        update_query = f"""
            update projects set
                name = '{name}', twitterUrl = '{twitterUrl}', twitterProfileImage = '{twitterProfileImage}', hasTime = '{hasTime}',
                mintDate = {mintDate}, 
                supply = '{supply}', wlPrice = '{wlPrice}', pubPrice = '{pubPrice}', blockchain = '{blockchain}',  
                noUpdate = '{noUpdate}',
                lastUpdated = concat(cast(UNIX_TIMESTAMP() as char),'000')
            where id = '{id}'
        """
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(update_query)
                    conn.commit()
            return {"status":"OK"}
        except Exception as e:
            conn.rollback()
            print(e)
            return {"status": "ERROR", "msg": e}

    def delete_project(db, form):
        id = form["id"]

        check_query = f"""
            SELECT COUNT(*) cnt FROM recommends WHERE projectId = '{id}'
        """
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(check_query)
                results = cursor.fetchall()
                if any(result['cnt'] > 0 for result in results):
                    return {"status": "ERROR", "msg": "Cannot delete project with existing recommends"}

        delete_query = f"""
            delete from projects
            where id = '{id}'
        """
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(delete_query)
                    conn.commit()
            return {"status":"OK"}
        except Exception as e:
            conn.rollback()
            print(e)
            return {"status": "ERROR", "msg": e}

    def select_user_projects(db, reg_user):
        select_query = f"""
            SELECT
                id, 
                name, 
                discordUrl,
                twitterUrl,  
                twitterProfileImage,  
                supply,  
                wlPrice,  
                pubPrice,  
                blockchain,  
                case when mintDate = 'TBA' then mintDate else FROM_UNIXTIME(mintDate/1000, '%Y-%m-%dT%H:%i') end mintDate,
                regUser,
                noUpdate  
             FROM projects 
             WHERE 1=1 
             AND CASE WHEN '{reg_user}' = '으노아부지#2642' then regUser != 'SearchFI'  else regUser = '{reg_user}' end
             ORDER BY name ASC 
        """
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchall()
                return result
                
    # def merge_recommend(db, project_id, regUser, recommend_type):
    #     insert_query = f"""
    #         insert into recommends
    #         (
    #             projectId, regUser, recommendType
    #         ) 
    #         values 
    #         (
    #             '{project_id}', '{regUser}', '{recommend_type}'
    #         )
    #         ON DUPLICATE KEY UPDATE recommendType='{recommend_type}';
    #     """
    #     try:
    #         with db.get_connection() as conn:
    #             with conn.cursor() as cursor:
    #                 cursor.execute(insert_query)
    #                 conn.commit()
    #         return {"status":"OK"}
    #     except Exception as e:
    #         conn.rollback()
    #         print(e)
    #         return {"status": "ERROR", "msg": e}
    
    def search_projects_by_name(db, project_name):
        project_name = f"%{project_name}%"
        select_query = f"""
            SELECT
                id,
                name,
                twitterUrl,
                twitterProfileImage,
                supply,
                wlPrice,
                pubPrice,
                blockchain,
                FROM_UNIXTIME(mintDate/1000, '%Y-%m-%dT%H:%i') mintDate,
                regUser
            FROM projects
            WHERE name LIKE '{project_name}'
            ORDER BY name ASC
        """

        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(select_query)
                    result = cursor.fetchall()
                    return result
        except Exception as e:
            print(e)
            return None
        
    def search_projects_by_twitter(db, twitter_url):
        twitter_url = f"%{twitter_url}%"
        select_query = f"""
            SELECT
                id,
                name,
                twitterUrl,
                twitterProfileImage,
                supply,
                wlPrice,
                pubPrice,
                blockchain,
                FROM_UNIXTIME(mintDate/1000, '%Y-%m-%dT%H:%i') mintDate,
                regUser
            FROM projects
            WHERE twitterUrl LIKE '{twitter_url}'
            ORDER BY name ASC
        """
        
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(select_query)
                    result = cursor.fetchall()
                    return result
        except Exception as e:
            print(e)
            return None

class ProjectModel(BaseModel):
    name: str = Field(..., example="My Project")
    twitterUrl: str = Field(..., example="https://twitter.com/myproject")
    twitterProfileImage: str = Field(..., example="https://example.com/profile.jpg")
    mintDate: str = Field(..., example="2023-05-01 23:00:00")
    supply: int = Field(..., example=10000)
    wlPrice: float = Field(..., example=0.05)
    pubPrice: float = Field(..., example=0.1)
    discordUrl: str = Field("None", example="https://discord.com/myproject")
    blockchain: str = Field("ETH", example="ETH")


app = FastAPI()
db = Database(mysql_ip, mysql_port, mysql_id, mysql_passwd, mysql_db)

@app.get("/")
def read_root():
    return ""

# @app.get("/good/{project_id}/{dc_id}")
# def good_item(project_id: str, dc_id: str):
#     result = Queries.merge_recommend(db, project_id, dc_id, 'UP')
#     html = """
#     <html>
#         <script>
#             alert("It's been recommended.");
#             window.close();
#         </script>
#     </html>
#     """
#     return HTMLResponse(content=html)

# @app.get("/bad/{project_id}/{dc_id}")
# def good_item(project_id: str, dc_id: str):
#     result = Queries.merge_recommend(db, project_id, dc_id, 'DOWN')
#     html = """
#     <html>
#         <script>
#             alert("It's not recommended.");
#             window.close();
#         </script>
#     </html>
#     """
#     return HTMLResponse(content=html)

app.mount("/static", StaticFiles(directory=os.getenv("STATIC_FOLDER")), name="static")
templates = Jinja2Templates(directory=os.getenv("TEMPLATES_FOLDER"))

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
SEARCHFI_BOT_DOMAIN = os.getenv("SEARCHFI_BOT_DOMAIN")
DISCORD_REDIRECT_URI = f"{SEARCHFI_BOT_DOMAIN}/discord-callback"

@app.get("/discord-callback/register")
async def reg_discord_callback(request: Request, code: str):
    try:
        headers = { 
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": f"{DISCORD_REDIRECT_URI}/register",
            "scope": "identify"
        }
        response = requests.post("https://discord.com/api/oauth2/token", headers=headers, data=data)
        response.raise_for_status()
        access_token = response.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        response = requests.get("https://discord.com/api/users/@me", headers=headers)
        response.raise_for_status()
        user = response.json()

        today = datetime.datetime.now().date()
        date_string = today.strftime("%Y-%m-%d")
        return templates.TemplateResponse("register.html", {"request": request, "user": user, "today": date_string})
    except Exception as e:
        print(e)
        return templates.TemplateResponse("error.html", {"request": request})

@app.get("/discord-callback/modify")
async def modify_discord_callback(request: Request, code: str):
    try:
        headers = { 
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": f"{DISCORD_REDIRECT_URI}/modify",
            "scope": "identify"
        }
        response = requests.post("https://discord.com/api/oauth2/token", headers=headers, data=data)
        response.raise_for_status()
        access_token = response.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        response = requests.get("https://discord.com/api/users/@me", headers=headers)
        response.raise_for_status()
        user = response.json()
        print(f"{user['username']}#{user['discriminator']}")
        result = Queries.select_user_projects(db, f"{user['username']}#{user['discriminator']}")
        
        today = datetime.datetime.now().date()
        date_string = today.strftime("%Y-%m-%d")
        return templates.TemplateResponse("modify.html", {"request": request, "user": user, "projects": result, "today": date_string})
    except Exception as e:
        print(e)
        return templates.TemplateResponse("error.html", {"request": request})
        
@app.post("/regist")
async def regist_submit(request: Request):
    unique_id = uuid.uuid4()
    form_data = await request.form()
    result = Queries.insert_project(db, unique_id, form_data)
    if result["status"] == "OK":
        comment = "Registration completed!"
    else:
        msg = result['msg']
        comment = f"Registration error: {msg}"
        print(comment)
        
    html = f"""
    <html>
        <script>
            parent.winClose('{comment}')
        </script>
    </html>
    """
    return HTMLResponse(content=html)

@app.post("/update")
async def update_submit(request: Request):
    form_data = await request.form()
    result = Queries.update_project(db, form_data)
    if result["status"] == "OK":
        comment = "Update completed!"
    else:
        msg = result['msg']
        comment = f"Update error: {msg}"
        
    html = f"""
    <html>
        <script>
            parent.winClose('{comment}')
        </script>
    </html>
    """
    
    return HTMLResponse(content=html)

@app.post("/delete")
async def delete_submit(request: Request):
    form_data = await request.form()
    result = Queries.delete_project(db, form_data)
    if result["status"] == "OK":
        comment = "Delete completed!"
    else:
        msg = result['msg']
        comment = f"Delete error: {msg}"
        
    html = f"""
    <html>
        <script>
            parent.winClose('{comment}')
        </script>
    </html>
    """
    return HTMLResponse(content=html)

@app.get("/api/projects/search/{project_name}")
async def search_projects(project_name: str):
    try:
        projects = Queries.search_projects_by_name(db, project_name)
        if projects:
            return {"status": "OK", "data": projects}
        else:
            return {"status": "ERROR", "message": "No projects found"}
    except Exception as e:
        print(e)
        return {"status": "ERROR", "message": "An error occurred while searching for projects"}

@app.post("/api/project", summary="Create a new project", description="Create a new project with the given details")
async def create_project(project: ProjectModel):
    try:
        # URL-decode the parameters
        name = unquote(project.name)
        twitterUrl = unquote(project.twitterUrl)
        twitterProfileImage = unquote(project.twitterProfileImage)
        mintDate = unquote(project.mintDate)
        
        # Check for duplicate twitterUrl
        existing_project = Queries.search_projects_by_twitter(db, twitterUrl)
        if len(existing_project) > 0:
            return {"status": "ERROR", "message": "This project already exists"}

        # Generate a unique UUID for the project
        unique_id = uuid.uuid4()

        form_data = {
            "name": name,
            "twitterUrl": twitterUrl,
            "twitterProfileImage": twitterProfileImage,
            "mintDate": mintDate,
            "supply": project.supply,
            "wlPrice": project.wlPrice,
            "pubPrice": project.pubPrice,
            "discordUrl": project.discordUrl,
            "blockchain": project.blockchain,
            "regUser": "으노아부지#2642",  # Set a default user for API-created projects
        }

        result = Queries.insert_project(db, unique_id, form_data)

        if result["status"] == "OK":
            return JSONResponse(content={"status": "OK", "message": "Project created successfully"})
        else:
            return JSONResponse(content={"status": "ERROR", "message": "An error occurred while creating the project"})
    except Exception as e:
        print(e)
        return {"status": "ERROR", "message": "An error occurred while creating for projects"}
    
@app.post("/api/projects/bulk", summary="Create multiple projects", description="Create multiple projects with the given details")
async def create_projects(projects: List[ProjectModel]):
    results = []

    for project in projects:
        try:
            # URL-decode the parameters
            name = unquote(project.name)
            twitterUrl = unquote(project.twitterUrl)
            twitterProfileImage = unquote(project.twitterProfileImage)
            mintDate = unquote(project.mintDate)

            # Check for duplicate twitterUrl
            existing_project = Queries.search_projects_by_twitter(db, twitterUrl)
            if len(existing_project) > 0:
                results.append({"status": "ERROR", "message": f"Project {name} already exists"})
                continue

            # Generate a unique UUID for the project
            unique_id = uuid.uuid4()

            form_data = {
                "name": name,
                "discordUrl": project.discordUrl,
                "twitterUrl": twitterUrl,
                "twitterProfileImage": twitterProfileImage,
                "mintDate": mintDate,
                "supply": project.supply,
                "wlPrice": project.wlPrice,
                "pubPrice": project.pubPrice,
                "blockchain": project.blockchain,
                "regUser": "으노아부지#2642",  # Set a default user for API-created projects
            }

            print(form_data)

            result = Queries.insert_project(db, unique_id, form_data)
            results.append(result)

        except Exception as e:
            print(e)
            results.append({"status": "ERROR", "message": f"An error occurred while creating project {project.name}"})

    return results