# AI回答自動生成サービス
import os
import openai
from typing import Dict, Any, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class AutoAnswerService:
    """AIによる回答自動生成を行うサービス"""
    
    def __init__(self):
        self.api_key = os.getenv("API_KEY")
        openai.api_key = self.api_key
        self.model = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
    
    async def generate_answers(self, project_name: str, questions: List[Dict[str, Any]], canvas_data: Dict[str, Any]) -> Dict[str, Any]:
        """質問に対するAI回答を生成"""
        try:
            # プロンプトを構築
            prompt = self._build_answer_generation_prompt(project_name, questions, canvas_data)
            
            # OpenAI APIを呼び出し
            response = await self._call_openai_api(prompt)
            
            # レスポンスを解析
            answers = self._parse_answer_response(response)
            
            return {
                "success": True,
                "answers": answers,
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"AI回答生成エラー: {e}")
            return {
                "success": False,
                "message": f"回答生成に失敗しました: {str(e)}"
            }
    
    def _build_answer_generation_prompt(self, project_name: str, questions: List[Dict[str, Any]], canvas_data: Dict[str, Any]) -> str:
        """回答生成用のプロンプトを構築"""
        
        # リーンキャンバスの各項目を取得
        field = canvas_data.get("field", {})
        
        # 最初のedit_idのfieldデータを取得
        canvas_field = None
        if field:
            first_key = next(iter(field))
            canvas_field = field[first_key]
        
        prompt = f"""
あなたは新規事業開発の専門家です。以下のリーンキャンバスと質問に対して、具体的で実用的な回答を生成してください。

## プロジェクト名
{project_name}

## リーンキャンバスの内容
"""
        
        # 各項目の内容を追加
        if canvas_field:
            for key, value in canvas_field.items():
                if value:
                    prompt += f"- {key}: {value}\n"
        
        prompt += f"""
## 回答すべき質問
"""
        
        # 各質問を追加
        for i, question_data in enumerate(questions, 1):
            question_text = question_data.get("question", "")
            perspective = question_data.get("perspective", "")
            prompt += f"""
質問{i}: {question_text}
分析観点: {perspective}
"""
        
        prompt += """
## 回答の要件
- 各質問に対して2-3行程度の具体的で実用的な回答を生成してください
- リーンキャンバスの内容を踏まえた、現実的で実行可能な内容にしてください
- 専門用語は避け、分かりやすい表現を使用してください
- ユーザーが実際に行動に移せるような具体的な提案を含めてください

## 出力形式
以下のJSON形式で5つの回答を出力してください：

{
  "answers": [
    "回答1の内容",
    "回答2の内容", 
    "回答3の内容",
    "回答4の内容",
    "回答5の内容"
  ]
}

各回答は以下の点を意識して作成してください：
- 質問の内容に直接的に答える
- リーンキャンバスの内容との整合性を保つ
- 具体的で実行可能な提案を含む
- 2-3行程度の適切な長さ
- 建設的で前向きな内容
"""
        
        return prompt
    
    async def _call_openai_api(self, prompt: str) -> str:
        """OpenAI APIを呼び出し"""
        try:
            client = openai.OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "あなたは新規事業開発の専門家です。リーンキャンバスの分析と改善提案を行います。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"OpenAI API呼び出しエラー: {e}")
            raise e
    
    def _parse_answer_response(self, response: str) -> List[str]:
        """OpenAIのレスポンスを解析して回答リストを抽出"""
        try:
            # レスポンスからJSON部分を抽出
            import json
            import re
            
            # JSONパターンを検索
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                parsed = json.loads(json_str)
                return parsed.get("answers", [])
            else:
                # JSONが見つからない場合は、レスポンス全体をパースしてみる
                parsed = json.loads(response)
                return parsed.get("answers", [])
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析エラー: {e}")
            # フォールバック: 基本的な回答形式で返す
            return [
                "リーンキャンバスの内容を踏まえて、具体的な改善策を検討する必要があります。",
                "顧客セグメントの定義をより明確にし、ターゲティング戦略を強化しましょう。",
                "価値提案の差別化要因を明確化し、競合優位性を高めることが重要です。",
                "収益モデルの持続可能性を確保し、コスト構造とのバランスを取る必要があります。",
                "主要指標の設定を見直し、ビジネスの成功を適切に測定できるようにしましょう。"
            ]
