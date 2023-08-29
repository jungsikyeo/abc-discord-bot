import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os as operating_system

# Discord API 토큰
discord_api_token = operating_system.getenv("SEARCHFI_BOT_TOKEN")

# 구글시트 설정
sheet_name = "klaydice role"
file_name = "searchfi.json"

# 서버(길드) 정보 (서치파이: 961242951504261130 / 1073551537940476007, 으노아부지: 1069466891367751691 / 1117874376289824778)
guild_id = "1069466891367751691"
role_id = "1117874376289824778"

# 현재 날짜를 가져와 파일명에 사용합니다.
current_date = datetime.now().strftime("%Y%m%d")
log_file_name = f"klaydice_addrole_{current_date}.txt"

# 로그 파일을 열기 위한 context manager를 생성합니다.
with open(log_file_name, "w") as log_file:
    # 구글 시트 접근 설정
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(file_name, scope)
    client = gspread.authorize(creds)

    # 시트 열기
    sheet = client.open(sheet_name).sheet1
    user_list = sheet.get_all_records()

    for user_info in user_list:
        if 'discord_uid' in user_info:
            try:
                uid = int(user_info['discord_uid'])
            except ValueError:
                log_file.write(f"Invalid UID {user_info['discord_uid']}\n")
                continue

            # API 호출로 롤 부여 (PUT 메서드 사용)
            url = f"https://discord.com/api/v10/guilds/{guild_id}/members/{uid}/roles/{role_id}"
            headers = {"Authorization": f"Bot {discord_api_token}"}
            response = requests.put(url, headers=headers)

            if response.status_code == 204:
                log_file.write(f"Role assigned for UID {uid}\n")
            else:
                log_file.write(f"Failed to assign role for UID {uid}\n")
