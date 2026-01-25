#!/usr/bin/env python3
"""
Notion → Gemini → Slack 自動処理スクリプト

Notionデータベースの未処理アイテムを取得し、Gemini APIで処理して、
結果をSlackに通知します。
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from typing import Any

from config import load_config, AppConfig
from clients import NotionClient, GeminiClient, SlackClient
from clients.notion_client import NotionItem, NotionClientError
from clients.gemini_client import GeminiClientError
from clients.slack_client import SlackClientError


# ロギング設定
def setup_logging(verbose: bool = False) -> None:
    """ロギングを設定"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@dataclass
class ProcessingResult:
    """処理結果を表すデータクラス"""
    item: NotionItem
    success: bool
    gemini_result: str = ""
    error_message: str = ""


class NotionGeminiSlackPipeline:
    """Notion → Gemini → Slack パイプライン"""

    def __init__(self, config: AppConfig):
        self.config = config
        self.notion = NotionClient(config.notion)
        self.gemini = GeminiClient(config.gemini)
        self.slack = SlackClient(config.slack)
        self.logger = logging.getLogger(self.__class__.__name__)

    def _build_gemini_input(self, item: NotionItem) -> str:
        """Geminiに送信するテキストを構築"""
        parts = [f"# {item.title}"]

        for prop_name, prop_value in item.content.items():
            if prop_value:
                parts.append(f"\n## {prop_name}\n{prop_value}")

        return "\n".join(parts)

    def process_single_item(self, item: NotionItem) -> ProcessingResult:
        """
        単一アイテムを処理

        Args:
            item: 処理するNotionアイテム

        Returns:
            処理結果
        """
        self.logger.info(f"処理開始: {item.title} ({item.page_id})")

        try:
            # Gemini用の入力テキストを構築
            gemini_input = self._build_gemini_input(item)

            if not gemini_input.strip() or gemini_input.strip() == f"# {item.title}":
                self.logger.warning(f"コンテンツが空のためスキップ: {item.title}")
                return ProcessingResult(
                    item=item,
                    success=False,
                    error_message="コンテンツが空です",
                )

            # Geminiで処理
            gemini_result = self.gemini.process(gemini_input)

            if not gemini_result:
                return ProcessingResult(
                    item=item,
                    success=False,
                    error_message="Geminiから有効な応答がありませんでした",
                )

            # Slackに通知
            original_content = "\n".join(
                f"{k}: {v}" for k, v in item.content.items() if v
            )
            slack_success = self.slack.send_processed_result(
                title=item.title,
                original_content=original_content,
                processed_result=gemini_result,
                notion_url=item.url,
            )

            if not slack_success:
                self.logger.warning(f"Slack通知に失敗: {item.title}")

            # Notionの処理済みフラグを更新
            notion_update_success = self.notion.mark_as_processed(item.page_id)

            if not notion_update_success:
                self.logger.warning(f"Notion更新に失敗: {item.title}")

            return ProcessingResult(
                item=item,
                success=True,
                gemini_result=gemini_result,
            )

        except GeminiClientError as e:
            error_msg = str(e)
            self.logger.error(f"Gemini処理エラー: {error_msg}")
            return ProcessingResult(
                item=item,
                success=False,
                error_message=error_msg,
            )

        except Exception as e:
            error_msg = f"予期しないエラー: {e}"
            self.logger.error(error_msg, exc_info=True)
            return ProcessingResult(
                item=item,
                success=False,
                error_message=error_msg,
            )

    def run(self, dry_run: bool = False) -> list[ProcessingResult]:
        """
        パイプラインを実行

        Args:
            dry_run: Trueの場合、実際の処理は行わず対象アイテムを表示

        Returns:
            処理結果のリスト
        """
        self.logger.info("パイプライン開始")

        # 未処理アイテムを取得
        try:
            items = self.notion.get_unprocessed_items()
        except NotionClientError as e:
            self.logger.error(f"Notionからの取得に失敗: {e}")
            return []

        if not items:
            self.logger.info("未処理のアイテムはありません")
            return []

        self.logger.info(f"{len(items)}件の未処理アイテムを検出")

        if dry_run:
            self.logger.info("=== ドライラン: 以下のアイテムが処理対象 ===")
            for item in items:
                self.logger.info(f"  - {item.title} ({item.page_id})")
            return []

        # 各アイテムを処理
        results: list[ProcessingResult] = []
        for item in items:
            result = self.process_single_item(item)
            results.append(result)

            # エラー時はSlackにエラー通知（オプション）
            if not result.success and result.error_message:
                try:
                    self.slack.send_error_notification(
                        title=item.title,
                        error_message=result.error_message,
                        notion_url=item.url,
                    )
                except SlackClientError:
                    self.logger.warning("エラー通知の送信にも失敗しました")

        # サマリーをログ出力
        success_count = sum(1 for r in results if r.success)
        fail_count = len(results) - success_count
        self.logger.info(f"処理完了: 成功={success_count}, 失敗={fail_count}")

        return results


def main():
    """メインエントリポイント"""
    parser = argparse.ArgumentParser(
        description="Notion → Gemini → Slack 自動処理スクリプト"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="詳細ログを出力",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際の処理は行わず、対象アイテムを表示",
    )
    args = parser.parse_args()

    # ロギング設定
    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)

    try:
        # 設定を読み込み
        config = load_config()
        logger.info("設定を読み込みました")

        # パイプラインを実行
        pipeline = NotionGeminiSlackPipeline(config)
        results = pipeline.run(dry_run=args.dry_run)

        # 終了コード
        if args.dry_run:
            sys.exit(0)

        if not results:
            sys.exit(0)

        # 全て成功した場合は0、1つでも失敗があれば1
        if all(r.success for r in results):
            sys.exit(0)
        else:
            sys.exit(1)

    except ValueError as e:
        logger.error(f"設定エラー: {e}")
        sys.exit(2)

    except KeyboardInterrupt:
        logger.info("処理が中断されました")
        sys.exit(130)

    except Exception as e:
        logger.error(f"予期しないエラー: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
