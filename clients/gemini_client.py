"""
Google Gemini APIクライアント

system_instructionを使用してGemsのような役割設定が可能。
"""
from __future__ import annotations

import logging
from typing import Any

import google.generativeai as genai
from google.generativeai.types import GenerationConfig

from config import GeminiConfig

logger = logging.getLogger(__name__)


class GeminiClientError(Exception):
    """Gemini API関連のエラー"""
    pass


class GeminiClient:
    """Google Gemini APIクライアント"""

    def __init__(self, config: GeminiConfig):
        self.config = config

        # APIキーを設定
        genai.configure(api_key=config.api_key)

        # モデルを初期化（system_instructionを設定）
        self.model = genai.GenerativeModel(
            model_name=config.model,
            system_instruction=config.system_instruction,
        )

        logger.info(f"Geminiモデル '{config.model}' を初期化しました")
        logger.debug(f"System Instruction: {config.system_instruction[:100]}...")

    def process(
        self,
        content: str,
        generation_config: GenerationConfig | None = None,
    ) -> str:
        """
        コンテンツをGeminiで処理

        Args:
            content: 処理するテキスト
            generation_config: 生成設定（オプション）

        Returns:
            Geminiの応答テキスト

        Raises:
            GeminiClientError: API呼び出しに失敗した場合
        """
        if not content or not content.strip():
            logger.warning("空のコンテンツが渡されました")
            return ""

        logger.info(f"Gemini APIにリクエスト送信中... (入力: {len(content)}文字)")

        # デフォルトの生成設定
        if generation_config is None:
            generation_config = GenerationConfig(
                temperature=0.7,
                top_p=0.95,
                top_k=40,
                max_output_tokens=8192,
            )

        try:
            response = self.model.generate_content(
                content,
                generation_config=generation_config,
            )

            # 応答のテキストを取得
            if response.text:
                result = response.text
                logger.info(f"Gemini API応答を受信 (出力: {len(result)}文字)")
                return result
            else:
                # ブロックされた場合などの処理
                if response.prompt_feedback:
                    logger.warning(f"プロンプトフィードバック: {response.prompt_feedback}")
                raise GeminiClientError("Gemini APIから有効な応答を取得できませんでした")

        except Exception as e:
            if isinstance(e, GeminiClientError):
                raise
            logger.error(f"Gemini APIエラー: {e}")
            raise GeminiClientError(f"Gemini API呼び出しに失敗: {e}") from e

    def process_with_custom_instruction(
        self,
        content: str,
        custom_system_instruction: str,
    ) -> str:
        """
        カスタムのsystem_instructionで一時的に処理

        特定のアイテムに対して異なる役割で処理したい場合に使用。

        Args:
            content: 処理するテキスト
            custom_system_instruction: このリクエスト専用のシステム指示

        Returns:
            Geminiの応答テキスト
        """
        logger.info("カスタムシステム指示でモデルを一時作成...")

        temp_model = genai.GenerativeModel(
            model_name=self.config.model,
            system_instruction=custom_system_instruction,
        )

        try:
            response = temp_model.generate_content(content)

            if response.text:
                return response.text
            else:
                raise GeminiClientError("Gemini APIから有効な応答を取得できませんでした")

        except Exception as e:
            if isinstance(e, GeminiClientError):
                raise
            logger.error(f"Gemini APIエラー: {e}")
            raise GeminiClientError(f"Gemini API呼び出しに失敗: {e}") from e
