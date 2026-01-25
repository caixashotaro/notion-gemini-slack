"""
設定管理モジュール

環境変数から設定を読み込み、バリデーションを行う。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

# .envファイルを読み込み
load_dotenv()


@dataclass(frozen=True)
class NotionConfig:
    """Notion API設定"""
    api_key: str
    database_id: str
    status_property: str  # 処理済みフラグのプロパティ名
    content_properties: list[str]  # Geminiに送るプロパティ名のリスト


@dataclass(frozen=True)
class GeminiConfig:
    """Gemini API設定"""
    api_key: str
    model: str
    system_instruction: str


@dataclass(frozen=True)
class SlackConfig:
    """Slack設定"""
    webhook_url: str
    channel: Optional[str] = None


@dataclass(frozen=True)
class AppConfig:
    """アプリケーション全体の設定"""
    notion: NotionConfig
    gemini: GeminiConfig
    slack: SlackConfig


def _get_required_env(key: str) -> str:
    """必須の環境変数を取得。未設定の場合は例外を発生"""
    value = os.getenv(key)
    if not value:
        raise ValueError(f"環境変数 {key} が設定されていません")
    return value


def _get_optional_env(key: str, default: str = "") -> str:
    """オプションの環境変数を取得"""
    return os.getenv(key, default)


# システムプロンプトのデフォルト値（.envで設定しない場合はここを編集）
DEFAULT_SYSTEM_INSTRUCTION = """
命令
あなたは優秀なプロジェクトマネージャー兼書記です。提供された会議の文字起こしデータを分析し、以下のフォーマットに従って明確かつ構造化された議事録を作成してください。

出力フォーマットと記載ルール
1. 全体の目的
このミーティング（または記録）が何のために行われたのか、1〜2文で簡潔に定義してください。
最終的なゴールが何かを明記してください。
2. エグゼクティブサマリー（改善の経緯と詳細進捗）
会議全体の内容を、項目数を限定せずに可能な限り詳しく要約してください。
単なる結果の列挙ではなく、**「改善の流れ（どのような経緯でその結論に至ったか）」**が分かるように記載してください。
特に進捗に関しては、現状のステータスと変化点を漏らさず記述してください。
3. 重要な質疑応答・検収要件（会話形式）
「検収（承認・OKが出る基準）」や「仕様の確認」に関するやり取りを重点的に抽出してください。
誰が何を懸念し、どう回答されたかが分かるよう、以下の会話形式で記載してください。
Q（質問/懸念）: [具体的な質問内容]
A（回答/決定）: [回答内容および決定した検収基準]
4. 決定されたタスク（ToDo）
具体的なアクションアイテムを抽出してください。可能な限り担当者を明記してください。

5. 全体のスケジュール感
会話に出てきた期限、マイルストーン、次回の予定などを時系列で整理してください。
具体的な日付がない場合でも、「来週中」「○○の後」といった時間的な文脈を拾ってください。
""".strip()


def load_config() -> AppConfig:
    """
    環境変数から設定を読み込み、AppConfigを返す。

    Raises:
        ValueError: 必須の環境変数が設定されていない場合
    """
    # Notion設定
    content_props_raw = _get_optional_env("NOTION_CONTENT_PROPERTIES", "タイトル,本文")
    content_properties = [p.strip() for p in content_props_raw.split(",") if p.strip()]

    notion_config = NotionConfig(
        api_key=_get_required_env("NOTION_API_KEY"),
        database_id=_get_required_env("NOTION_DATABASE_ID"),
        status_property=_get_optional_env("NOTION_STATUS_PROPERTY", "処理済み"),
        content_properties=content_properties,
    )

    # Gemini設定
    system_instruction = _get_optional_env("GEMINI_SYSTEM_INSTRUCTION")
    if not system_instruction:
        system_instruction = DEFAULT_SYSTEM_INSTRUCTION
    # \n を実際の改行に変換
    system_instruction = system_instruction.replace("\\n", "\n")

    gemini_config = GeminiConfig(
        api_key=_get_required_env("GEMINI_API_KEY"),
        model=_get_optional_env("GEMINI_MODEL", "gemini-1.5-pro"),
        system_instruction=system_instruction,
    )

    # Slack設定
    slack_config = SlackConfig(
        webhook_url=_get_required_env("SLACK_WEBHOOK_URL"),
        channel=_get_optional_env("SLACK_CHANNEL") or None,
    )

    return AppConfig(
        notion=notion_config,
        gemini=gemini_config,
        slack=slack_config,
    )
