# リーンキャンバス整合性確認サービス
import os
import openai
from typing import Dict, Any, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ConsistencyService:
    """リーンキャンバスの整合性確認と改善提案を行うサービス"""
    
    def __init__(self):
        # OpenAI設定
        self.api_key = os.getenv("API_KEY")
        if not self.api_key:
            logger.warning("API_KEYが設定されていません")
        
        openai.api_key = self.api_key
        self.model = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
    
    async def analyze_canvas_consistency(self, canvas_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        リーンキャンバスの整合性を分析し、改善のための質問を生成
        
        Args:
            canvas_data: リーンキャンバスのデータ
            
        Returns:
            整合性分析結果と改善提案
        """
        try:
            # プロンプトを構築
            prompt = self._build_consistency_analysis_prompt(canvas_data)
            
            # OpenAI APIを呼び出し
            response = await self._call_openai_api(prompt)
            
            # レスポンスを解析
            analysis_result = self._parse_consistency_response(response)
            
            return {
                "success": True,
                "analysis": analysis_result,
                "analyzed_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"整合性分析エラー: {e}")
            return {
                "success": False,
                "message": f"整合性分析に失敗しました: {str(e)}"
            }
    
    def _build_consistency_analysis_prompt(self, canvas_data: Dict[str, Any]) -> str:
        """整合性分析用のプロンプトを構築"""
        
        # リーンキャンバスの各項目を取得
        # get_canvas_detailsから返されるデータ構造: {edit_id: field}
        field = canvas_data.get("field", {})
        
        # 最初のedit_idのfieldデータを取得（通常は1つしかない）
        canvas_field = None
        if field:
            # 最初のキーの値を取得
            first_key = next(iter(field))
            canvas_field = field[first_key]
        
        prompt = f"""
あなたは新規事業開発の専門家です。以下のリーンキャンバスを分析し、整合性の問題や改善点を特定してください。

## 分析対象のリーンキャンバス
プロジェクト名: {canvas_data.get('project_name', 'N/A')}

### 各項目の内容
"""
        
        # 各項目の内容を追加
        if canvas_field:
            for key, value in canvas_field.items():
                if value:
                    prompt += f"- {key}: {value}\n"
        
        prompt += """
## 分析の観点

### 1. 整合性の問題
- 各項目間の論理的な矛盾
- 前提条件の不一致
- 数値や規模の不整合

### 2. 観点の不足
- 重要な要素の欠如
- 考慮すべきリスクや課題
- 競合分析の深さ

### 3. 実現可能性
- 技術的・経営的な実現可能性
- リソースの妥当性

## 出力形式
以下のJSON形式で5つの質問を出力してください。各質問は具体的で建設的であるべきです：

{
  "Q1": {
    "question": "質問1",
    "perspective": "顧客課題と解決策の整合性"
  },
  "Q2": {
    "question": "質問2",
    "perspective": "顧客セグメントの定義とターゲティング"
  },
  "Q3": {
    "question": "質問3",
    "perspective": "価値提案と競合優位性"
  },
  "Q4": {
    "question": "質問4",
    "perspective": "ビジネスモデルの持続可能性"
  },
  "Q5": {
    "question": "質問5",
    "perspective": "主要指標の適切性"
  }
}

質問は以下の点を意識して作成してください：
- 事業・サービスの内容に踏み込んだ具体的で実用的な改善提案につながる内容
- 事業の成功確率を高める視点
- 各項目間の関係性を明確にする内容（例えば、スマホ保有率が低い高齢者層をセグメントにしているにもかかわらず、スマホでのサービスを提供してしまっていないか？）
- 今後の計画等に関する内容ではなく、事業・サービスの内容に関する質問
- ユーザーはまだ調査やインタビューを行っていない初期仮説である前提
- ユーザーが2-3行で答えられる内容
- YES/NOで答えられる項目ではなく、What/How/Why/When/Where/Who/How much/How many/How often/How long/How muchのような質問
- ユーザーに寄り添ったやわらかい表現
- 各質問の分析観点には、必ずリーンキャンバスの見出し（「顧客課題」「顧客セグメント」「提供価値」等）を含めてください


JSONのみを出力し、説明文は絶対に含めないでください。
"""
        
        return prompt
    
    async def _call_openai_api(self, prompt: str) -> str:
        """OpenAI APIを呼び出し"""
        try:
            client = openai.OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "あなたは新規事業開発の専門家です。リーンキャンバスの整合性分析と改善提案を行います。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"OpenAI API呼び出しエラー: {e}")
            raise e
    
    def _parse_consistency_response(self, response: str) -> Dict[str, Dict[str, str]]:
        """OpenAIのレスポンスを解析してJSONを抽出"""
        try:
            # レスポンスからJSON部分を抽出
            import json
            import re
            
            # JSONパターンを検索
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                return json.loads(json_str)
            else:
                # JSONが見つからない場合は、レスポンス全体をパースしてみる
                return json.loads(response)
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析エラー: {e}")
            # フォールバック: 基本的な質問形式で返す
            return {
                "Q1": {
                    "question": "各項目間の論理的な整合性に問題はありませんか？",
                    "perspective": "顧客課題と解決策の整合性"
                },
                "Q2": {
                    "question": "重要な観点や要素が不足していませんか？",
                    "perspective": "顧客セグメントの定義とターゲティング"
                },
                "Q3": {
                    "question": "技術的・経営的な実現可能性は適切に評価されていますか？",
                    "perspective": "価値提案と競合優位性"
                },
                "Q4": {
                    "question": "競合分析は十分に深く行われていますか？",
                    "perspective": "ビジネスモデルの持続可能性"
                },
                "Q5": {
                    "question": "全体的な事業戦略として一貫性がありますか？",
                    "perspective": "主要指標の適切性"
                }
            }
