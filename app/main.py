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
from pycookiecheat import chrome_cookies

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
        mintDate = form["mintDate"]
        supply = form["supply"]
        wlPrice = form["wlPrice"]
        pubPrice = form["pubPrice"]
        blockchain = form["blockchain"]
        regUser = form["regUser"]

        insert_query = f"""
            insert into projects
            (
                id, name, discordUrl, twitterUrl, twitterProfileImage, mintDate, 
                supply, wlPrice, pubPrice, blockchain, hasTime, 
                regUser, isAlphabot, lastUpdated, dateCreated
            ) 
            values 
            (
                '{uuid}', '{name}', '{discordUrl}', '{twitterUrl}', '{twitterProfileImage}', concat(cast(UNIX_TIMESTAMP('{mintDate}') as char),'000'), 
                '{supply}', '{wlPrice}', '{pubPrice}', '{blockchain}', 'True', 
                '{regUser}', 'N', concat(cast(UNIX_TIMESTAMP() as char),'000'), concat(cast(UNIX_TIMESTAMP() as char),'000')
            )
        """
        print(insert_query)
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
    
    def update_project(db, form):
        id = form["id"]
        name = form["name"]
        twitterUrl = form["twitterUrl"]
        twitterProfileImage = form["twitterProfileImage"]
        mintDate = form["mintDate"]
        supply = form["supply"]
        wlPrice = form["wlPrice"]
        pubPrice = form["pubPrice"]
        blockchain = form["blockchain"]
        regUser = form["regUser"]

        update_query = f"""
            update projects set
                name = '{name}', twitterUrl = '{twitterUrl}', twitterProfileImage = '{twitterProfileImage}', mintDate = concat(cast(UNIX_TIMESTAMP('{mintDate}') as char),'000'), 
                supply = '{supply}', wlPrice = '{wlPrice}', pubPrice = '{pubPrice}', blockchain = '{blockchain}',  
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
                FROM_UNIXTIME(mintDate/1000, '%Y-%m-%dT%H:%i') mintDate,
                regUser  
             FROM projects 
             WHERE 1=1 
             AND regUser = '{reg_user}' 
             ORDER BY name ASC 
        """
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchall()
                return 
                
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
        
    
        
    def set_winner(db, dc_id, data):
        def is_json_key_present(json_data, key):
            try:
                buf = str(json_data[key])
            except Exception as e:
                print("parse error:",e)
                return ""

            return buf
        
        try:
            index = 0
            with db.get_connection() as conn:
                for project in data["projects"]:
                    id = is_json_key_present(project, "_id")
                    is_winner = is_json_key_present(project, "isWinner")
                    if is_winner == "True":
                        project_id = id
                        regUser = dc_id
                        recommend_type = "UP"

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
                        with conn.cursor() as cursor:
                            cursor.execute(insert_query)
                        

                conn.commit()
                
            return {"status":"OK"}
        except Exception as e:
            conn.rollback()
            print(e)
            return {"status": "ERROR", "msg": e}



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

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID_DEV")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET_DEV")
DISCORD_REDIRECT_URI = "https://code.yjsdev.tk/discord-callback"

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


class CookieData(BaseModel):
    cookie: str

@app.post("/send-cookie")
async def send_cookie(cookie_data: CookieData):
    if not cookie_data.cookie:
        print("No cookie received")
        return JSONResponse(content={"status": "ERROR", "message": "No cookie received"}, status_code=422)
    print("cookie : ", cookie_data.cookie)

    if os.name == "nt":
        profiles_dir = os.path.join(os.environ["USERPROFILE"], "AppData", "Local", "Google", "Chrome", "User Data")
    elif os.name == "posix":
        profiles_dir = os.path.expanduser("~/Library/Application Support/Google/Chrome")

    # 사용자 프로필 디렉터리에서 모든 프로필 찾기
    profiles = [name for name in os.listdir(profiles_dir) if os.path.isdir(os.path.join(profiles_dir, name)) and "Profile" in name or "Default" == name]

    # 각 프로필의 쿠키 파일 경로 가져오기
    isBreak = False
    for profile in profiles:
        if isBreak == True:
            break
        cookie_file = os.path.join(profiles_dir, profile, "Cookies")
        if os.path.isfile(cookie_file):
            print(f"Profile: {profile}, Cookie file: {cookie_file}")

            cj = chrome_cookies("https://www.alphabot.app", cookie_file)

            # 가져온 쿠키를 사용하여 API 호출
            alphabot_response = requests.get("https://www.alphabot.app/api/auth/session", cookies=cj)
            alphabot_response.raise_for_status()
            alphabot_session = alphabot_response.json()

            if alphabot_session and alphabot_session['connections']:
                for connection in alphabot_session['connections']:
                    if connection['name'] == cookie_data.dc_id:
                        isBreak = True
                        try:
                            today_timestamp = today_date() + "000"
                            tomorrow_timestamp = month_date() + "000"
                            print(today_timestamp, tomorrow_timestamp)
                            projects_response = requests.get(f"https://www.alphabot.app/api/projectData?calendar=true&startDate={today_timestamp}&endDate={tomorrow_timestamp}&selectedMonth=2&a=", cookies=cj)
                            projects_response.raise_for_status()
                            projects = projects_response.json()
                            result = Queries.set_winner(db, cookie_data.dc_id, projects)
                        except Exception as e:
                            print(e)
                            return templates.TemplateResponse("error.html")

    pass

def today_date():
    today = datetime.datetime.now().date()
    date_string = today.strftime("%Y-%m-%d 00:00:00")
    date_object = datetime.datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
    today_date = str(int(date_object.timestamp()))
    print("today:" + date_string)
    return str(today_date)

def month_date():
    month = (datetime.datetime.now() + datetime.timedelta(days=31)).date()
    date_string = month.strftime("%Y-%m-%d 23:59:59")
    date_object = datetime.datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
    month_date = str(int(date_object.timestamp()))
    print("month:" + date_string)
    return str(month_date)


@app.get("/discord-callback/mymint")
async def mymint_discord_callback(request: Request, code: str):
    result = None
    try:
        session = requests.Session()
        session.headers.update({ 
            "Content-Type": "application/x-www-form-urlencoded"
        })
        data = {
            "client_id": "1090169638765207574",
            "client_secret": "jCbUl3bYbyVOa9-U5YELAd90IOMBXKMm",
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": f"http://localhost:8080/discord-callback/mymint",
            "scope": "identify"
        }
        token_response = session.post("https://discord.com/api/oauth2/token", data=data)
        token_response.raise_for_status()
        access_token = token_response.json()["access_token"]

        session.headers.update({ 
            "Authorization": f"Bearer {access_token}"
        })
        user_response = session.get("https://discord.com/api/users/@me")
        user_response.raise_for_status()
        user_info = user_response.json()

        dc_id = f"{user_info['username']}#{user_info['discriminator']}"
        print('user_info', user_info)

            
        html = f"""
        <html>
            <script>
                // 클라이언트 측에서 쿠키 읽기
                function getCookie(name) {{
                    alert(document.cookie)
                    const value = "; " + document.cookie;
                    const parts = value.split("; " + name + "=");
                    if (parts.length === 2) return parts.pop().split(";").shift();
                }}

                // 쿠키 값을 가져온 후 서버로 전송
                const cookieValue = getCookie("https://www.alphabot.app");
                alert(cookieValue)
                fetch("http://localhost:8080/send-cookie", {{
                    method: "POST",
                    headers: {{
                        "Content-Type": "application/json"
                    }},
                    body: JSON.stringify({{ cookie: cookieValue}})
                }})
                .then(response => response.json())
                .then(result => {{
                    if (result.status === "OK") {{
                        alert("Your Mint Schedule Saved!");
                    }} else {{
                        alert("Mint Schedule Save Error!");
                    }}
                    //window.close();
                }});
            </script>
        </html>
        """
        return HTMLResponse(content=html)
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
        comment = "Registration error!"
        
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
        comment = "Update error!"
        
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
        comment = "Delete error!"
        
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