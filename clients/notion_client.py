"""
Notion APIクライアント

データベースからの未処理アイテム取得と処理済みフラグ更新を担当。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

from config import NotionConfig

logger = logging.getLogger(__name__)


@dataclass
class NotionItem:
    """Notionデータベースのアイテムを表すデータクラス"""
    page_id: str
    title: str
    content: dict[str, str]  # プロパティ名 -> 値のマッピング
    url: str


class NotionClientError(Exception):
    """Notion API関連のエラー"""
    pass


class NotionClient:
    """Notion APIクライアント"""

    BASE_URL = "https://api.notion.com/v1"
    API_VERSION = "2022-06-28"

    def __init__(self, config: NotionConfig):
        self.config = config
        self.headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Notion-Version": self.API_VERSION,
            "Content-Type": "application/json",
        }

    def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: dict | None = None,
    ) -> dict:
        """APIリクエストを実行"""
        url = f"{self.BASE_URL}{endpoint}"

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                json=json_data,
                timeout=30,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            error_body = ""
            try:
                error_body = e.response.json()
            except Exception:
                error_body = e.response.text
            logger.error(f"Notion API HTTPエラー: {e}, Response: {error_body}")
            raise NotionClientError(f"Notion APIエラー: {e}") from e

        except requests.exceptions.RequestException as e:
            logger.error(f"Notion APIリクエストエラー: {e}")
            raise NotionClientError(f"Notion API接続エラー: {e}") from e

    def _extract_property_value(self, prop: dict) -> str:
        """Notionプロパティから値を抽出"""
        prop_type = prop.get("type", "")

        if prop_type == "title":
            return "".join(
                t.get("plain_text", "") for t in prop.get("title", [])
            )

        elif prop_type == "rich_text":
            return "".join(
                t.get("plain_text", "") for t in prop.get("rich_text", [])
            )

        elif prop_type == "number":
            return str(prop.get("number", ""))

        elif prop_type == "select":
            select = prop.get("select")
            return select.get("name", "") if select else ""

        elif prop_type == "multi_select":
            return ", ".join(
                s.get("name", "") for s in prop.get("multi_select", [])
            )

        elif prop_type == "date":
            date = prop.get("date")
            if date:
                start = date.get("start", "")
                end = date.get("end", "")
                return f"{start} - {end}" if end else start
            return ""

        elif prop_type == "checkbox":
            return str(prop.get("checkbox", False))

        elif prop_type == "url":
            return prop.get("url", "") or ""

        elif prop_type == "email":
            return prop.get("email", "") or ""

        elif prop_type == "phone_number":
            return prop.get("phone_number", "") or ""

        elif prop_type == "people":
            return ", ".join(
                p.get("name", "") for p in prop.get("people", [])
            )

        elif prop_type == "relation":
            return ", ".join(
                r.get("id", "") for r in prop.get("relation", [])
            )

        else:
            logger.warning(f"未対応のプロパティタイプ: {prop_type}")
            return ""

    def _get_page_content(self, page_id: str) -> str:
        """ページのブロックコンテンツを取得"""
        try:
            response = self._make_request(
                "GET",
                f"/blocks/{page_id}/children?page_size=100",
            )

            blocks = response.get("results", [])
            content_parts = []

            for block in blocks:
                block_type = block.get("type", "")
                block_data = block.get(block_type, {})

                # テキスト系ブロックから内容を抽出
                if "rich_text" in block_data:
                    text = "".join(
                        t.get("plain_text", "")
                        for t in block_data.get("rich_text", [])
                    )
                    if text:
                        content_parts.append(text)

            return "\n".join(content_parts)

        except NotionClientError:
            logger.warning(f"ページ {page_id} のコンテンツ取得に失敗")
            return ""

    def get_unprocessed_items(self) -> list[NotionItem]:
        """
        未処理（Checkbox=False）のアイテムを取得

        Returns:
            未処理アイテムのリスト
        """
        logger.info("未処理アイテムを取得中...")

        # フィルタ: 指定されたCheckboxプロパティがFalse
        filter_condition = {
            "property": self.config.status_property,
            "checkbox": {
                "equals": False
            }
        }

        query_data = {
            "filter": filter_condition,
            "page_size": 100,  # 必要に応じて調整
        }

        response = self._make_request(
            "POST",
            f"/databases/{self.config.database_id}/query",
            json_data=query_data,
        )

        items = []
        for result in response.get("results", []):
            page_id = result.get("id", "")
            properties = result.get("properties", {})
            url = result.get("url", "")

            # タイトルを取得（titleタイプのプロパティを探す）
            title = ""
            for prop_name, prop_value in properties.items():
                if prop_value.get("type") == "title":
                    title = self._extract_property_value(prop_value)
                    break

            # 指定されたプロパティの値を取得
            content = {}
            for prop_name in self.config.content_properties:
                if prop_name in properties:
                    value = self._extract_property_value(properties[prop_name])
                    content[prop_name] = value

            # 「本文」プロパティがない場合、ページコンテンツを取得
            if "本文" in self.config.content_properties and not content.get("本文"):
                page_content = self._get_page_content(page_id)
                if page_content:
                    content["本文"] = page_content

            items.append(NotionItem(
                page_id=page_id,
                title=title or "(無題)",
                content=content,
                url=url,
            ))

        logger.info(f"{len(items)}件の未処理アイテムを取得")
        return items

    def mark_as_processed(self, page_id: str) -> bool:
        """
        アイテムを処理済みとしてマーク（Checkbox=True）

        Args:
            page_id: 更新するページのID

        Returns:
            成功した場合True
        """
        logger.info(f"ページ {page_id} を処理済みにマーク中...")

        update_data = {
            "properties": {
                self.config.status_property: {
                    "checkbox": True
                }
            }
        }

        try:
            self._make_request(
                "PATCH",
                f"/pages/{page_id}",
                json_data=update_data,
            )
            logger.info(f"ページ {page_id} を処理済みにマーク完了")
            return True

        except NotionClientError as e:
            logger.error(f"ページ {page_id} の更新に失敗: {e}")
            return False
