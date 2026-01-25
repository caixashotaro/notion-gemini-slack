import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("NOTION_API_KEY")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

# APIキーが有効か確認
r = requests.get(
    "https://api.notion.com/v1/users/me",
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Notion-Version": "2022-06-28"
    }
)
print(f"APIキー確認: {r.status_code}")
print(r.json())
