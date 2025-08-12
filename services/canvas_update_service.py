# リーンキャンバス更新案生成サービス
import os
import openai
from typing import Dict, Any, List
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class CanvasUpdateService:
    """AIによるリーンキャンバス更新案生成を行うサービス"""
    
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        openai.api_key = self.api_key
        self.model = os.getenv("OPENAI_MODEL", "gpt-4-turbo-preview")
    
    async def generate_canvas_update(self, project_name: str, canvas_data: Dict[str, Any], user_answers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """リーンキャンバスの更新案を生成"""
        try:
            prompt = self._build_canvas_update_prompt(project_name, canvas_data, user_answers)
            response = await self._call_openai_api(prompt)
            update_result = self._parse_canvas_update_response(response)
            
            return {
                "success": True,
                "updates": update_result["updates"],
                "updated_canvas": update_result["updated_canvas"],
                "generated_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"リーンキャンバス更新案生成エラー: {e}")
            return {
                "success": False,
                "message": f"更新案生成に失敗しました: {str(e)}"
            }
    
    def _build_canvas_update_prompt(self, project_name: str, canvas_data: Dict[str, Any], user_answers: List[Dict[str, Any]]) -> str:
        """リーンキャンバス更新案生成用のプロンプトを構築"""
        
        field = canvas_data.get("field", {})
        canvas_field = None
        if field:
            first_key = next(iter(field))
            canvas_field = field[first_key]
        
        prompt = f"""
あなたは新規事業開発の専門家です。以下のリーンキャンバスとユーザーの回答を分析して、リーンキャンバスの更新案を生成してください。

## プロジェクト名
{project_name}

## 現在のリーンキャンバスの内容
"""
        
        if canvas_field:
            for key, value in canvas_field.items():
                if value:
                    prompt += f"- {key}: {value}\n"
        
        prompt += f"""
## ユーザーの回答内容
"""
        
        for i, answer_data in enumerate(user_answers, 1):
            question = answer_data.get("question", "")
            answer = answer_data.get("answer", "")
            perspective = answer_data.get("perspective", "")
            prompt += f"""
質問{i}: {question}
分析観点: {perspective}
回答: {answer}
"""
        
        prompt += """
## 更新案生成の手順
1. ユーザーの回答から各リーンキャンバス要素の変更が必要かどうかを判断
2. 変更が必要な要素について具体的な修正案を考え
3. 各要素間の関係性を分析し、不整合がある要素を修正
4. 修正を加えた要素について、その理由を明確に説明
5. 修正を反映した完全なリーンキャンバスを作成

## 出力形式
以下の2つのJSONを出力してください：

### 1. 更新内容の詳細
```json
{
  "updates": [
    {
      "field": "Problem",
      "before": "現在のリーンキャンバスの実際の内容（上記で提供された内容）",
      "after": "変更後の内容", 
      "reason": "変更理由の説明"
    }
  ]
}
```

### 2. 更新後のリーンキャンバス
```json
{
  "updated_canvas": {
    "idea_name": "更新後の内容",
    "Problem": "更新後の内容",
    "Customer_Segments": "更新後の内容",
    "Unique_Value_Proposition": "更新後の内容",
    "Solution": "更新後の内容",
    "Channels": "更新後の内容",
    "Revenue_Streams": "更新後の内容",
    "Cost_Structure": "更新後の内容",
    "Key_Metrics": "更新後の内容",
    "Unfair_Advantage": "更新後の内容",
    "Early_Adopters": "更新後の内容",
    "Existing_Alternatives": "更新後の内容"
  }
}
```

## 重要事項
- 「before」フィールドには、上記で提供された現在のリーンキャンバスの実際の内容を正確に記載してください。「未記載」や「現在の課題」などの曖昧な表現は使用しないでください。
- ユーザーの回答と各要素間の整合性のみを重視し、具体的で実用的な改善案を提案してください
- 可能な限り、変更するfieldの数は少なくしてください
- 変更理由は明確で分かりやすく説明してください
- リーンキャンバスの12の要素すべてを含めてください
- 変更がない要素は、"updates"の中に含めないでください
- 各要素の内容は具体的で実用的な内容にしてください
"""
        
        return prompt
    
    async def _call_openai_api(self, prompt: str) -> str:
        """OpenAI APIを呼び出し"""
        try:
            client = openai.OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "あなたは新規事業開発の専門家です。リーンキャンバスの分析と新リーンキャンバスの提案を行います。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.7
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"OpenAI API呼び出しエラー: {e}")
            raise e
    
    def _parse_canvas_update_response(self, response: str) -> Dict[str, Any]:
        """OpenAIのレスポンスを解析して更新案を抽出"""
        try:
            import json
            import re
            
            updates_match = re.search(r'"updates":\s*\[.*?\]', response, re.DOTALL)
            updated_canvas_match = re.search(r'"updated_canvas":\s*\{.*?\}', response, re.DOTALL)
            
            updates = []
            updated_canvas = {}
            
            if updates_match:
                updates_text = "{" + updates_match.group() + "}"
                updates_data = json.loads(updates_text)
                updates = updates_data.get("updates", [])
            
            if updated_canvas_match:
                canvas_text = "{" + updated_canvas_match.group() + "}"
                canvas_data = json.loads(canvas_text)
                updated_canvas = canvas_data.get("updated_canvas", {})
            
            if not updates or not updated_canvas:
                try:
                    full_response = json.loads(response)
                    if not updates:
                        updates = full_response.get("updates", [])
                    if not updated_canvas:
                        updated_canvas = full_response.get("updated_canvas", {})
                except:
                    pass
            
            return {
                "updates": updates,
                "updated_canvas": updated_canvas
            }
                
        except Exception as e:
            logger.error(f"JSON解析エラー: {e}")
            return {
                "updates": [
                    {
                        "field": "Problem",
                        "before": "現在の課題",
                        "after": "改善された課題",
                        "reason": "ユーザーの回答に基づく改善"
                    }
                ],
                "updated_canvas": {
                    "idea_name": "更新されたアイデア名",
                    "Problem": "更新された課題",
                    "Customer_Segments": "更新された顧客セグメント",
                    "Unique_Value_Proposition": "更新された価値提案",
                    "Solution": "更新された解決策",
                    "Channels": "更新されたチャネル",
                    "Revenue_Streams": "更新された収益源",
                    "Cost_Structure": "更新されたコスト構造",
                    "Key_Metrics": "更新された主要指標",
                    "Unfair_Advantage": "更新された競争優位性",
                    "Early_Adopters": "更新されたアーリーアダプター",
                    "Existing_Alternatives": "更新された既存の代替品"
                }
            }
