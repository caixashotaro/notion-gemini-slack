"""
Slack通知クライアント

Incoming Webhookを使用してSlackに通知を送信。
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from config import SlackConfig

logger = logging.getLogger(__name__)


class SlackClientError(Exception):
    """Slack API関連のエラー"""
    pass


class SlackClient:
    """Slack Webhook クライアント"""

    def __init__(self, config: SlackConfig):
        self.config = config

    def send_message(
        self,
        text: str,
        blocks: list[dict] | None = None,
        attachments: list[dict] | None = None,
    ) -> bool:
        """
        Slackにメッセージを送信

        Args:
            text: メッセージ本文（blocksがない場合や通知に表示）
            blocks: Block Kit形式のリッチメッセージ（オプション）
            attachments: 添付データ（オプション）

        Returns:
            送信成功した場合True
        """
        logger.info("Slackにメッセージ送信中...")

        payload: dict[str, Any] = {"text": text}

        if blocks:
            payload["blocks"] = blocks

        if attachments:
            payload["attachments"] = attachments

        if self.config.channel:
            payload["channel"] = self.config.channel

        try:
            response = requests.post(
                self.config.webhook_url,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()

            # Slack Webhookは成功時 "ok" を返す
            if response.text == "ok":
                logger.info("Slackへのメッセージ送信成功")
                return True
            else:
                logger.warning(f"Slack応答: {response.text}")
                return False

        except requests.exceptions.HTTPError as e:
            logger.error(f"Slack HTTPエラー: {e}")
            raise SlackClientError(f"Slack送信エラー: {e}") from e

        except requests.exceptions.RequestException as e:
            logger.error(f"Slackリクエストエラー: {e}")
            raise SlackClientError(f"Slack接続エラー: {e}") from e

    def send_processed_result(
        self,
        title: str,
        original_content: str,
        processed_result: str,
        notion_url: str,
    ) -> bool:
        """
        処理結果をリッチフォーマットで送信

        Args:
            title: Notionアイテムのタイトル
            original_content: 元のコンテンツ（要約表示）
            processed_result: Geminiの処理結果
            notion_url: NotionページのURL

        Returns:
            送信成功した場合True
        """
        # 元コンテンツは長すぎる場合は切り詰め
        truncated_original = original_content
        if len(truncated_original) > 300:
            truncated_original = truncated_original[:300] + "..."

        # Block Kit形式でリッチなメッセージを構成
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📝 {title}",
                    "emoji": True,
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": processed_result[:3000],  # Slack制限に合わせて切り詰め
                }
            },
        ]

        # Notion URLがあればボタンを追加
        if notion_url:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "📄 Notionで開く",
                            "emoji": True,
                        },
                        "url": notion_url,
                    }
                ]
            })

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "🤖 _Gemini APIで自動処理されました_",
                }
            ]
        })

        # フォールバックテキスト
        fallback_text = f"📝 {title}\n\n{processed_result[:500]}..."

        return self.send_message(text=fallback_text, blocks=blocks)

    def send_error_notification(
        self,
        title: str,
        error_message: str,
        notion_url: str = "",
    ) -> bool:
        """
        エラー通知を送信

        Args:
            title: 処理対象のタイトル
            error_message: エラーメッセージ
            notion_url: NotionページのURL（オプション）

        Returns:
            送信成功した場合True
        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚠️ 処理エラー",
                    "emoji": True,
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*対象:* {title}\n*エラー:* {error_message}",
                }
            },
        ]

        if notion_url:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "📄 Notionで確認",
                            "emoji": True,
                        },
                        "url": notion_url,
                    }
                ]
            })

        return self.send_message(
            text=f"⚠️ 処理エラー: {title} - {error_message}",
            blocks=blocks,
        )
