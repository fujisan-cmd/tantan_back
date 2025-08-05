# リーンキャンバス関連のサービス
from typing import Dict, Any, List, Optional
from crud.projects import ProjectCRUD
from database import db_connection
from services.rag_service import RAGService
import logging

logger = logging.getLogger(__name__)

class CanvasService:
    """リーンキャンバス関連のビジネスロジック"""
    
    def __init__(self):
        self.project_crud = ProjectCRUD(db_connection)
        self.rag_service = RAGService()
        
        # リーンキャンバスフィールドの定義
        self.canvas_fields = [
            'problem', 'customer_segments', 'unique_value_proposition',
            'solution', 'channels', 'revenue_streams', 'cost_structure',
            'key_metrics', 'unfair_advantage', 'early_adopters', 'existing_alternatives'
        ]
        
        # フィールドの日本語名マッピング
        self.field_labels = {
            'problem': '課題',
            'customer_segments': '顧客セグメント',
            'unique_value_proposition': '独自の価値提案',
            'solution': 'ソリューション',
            'channels': 'チャネル',
            'revenue_streams': '収益の流れ',
            'cost_structure': 'コスト構造',
            'key_metrics': '主要指標',
            'unfair_advantage': '圧倒的優位性',
            'early_adopters': '早期アダプター',
            'existing_alternatives': '既存の代替'
        }
    
    async def create_project_with_canvas(self, user_id: int, project_name: str, 
                                       canvas_data: Dict[str, Any], update_comment: Optional[str] = None) -> Dict[str, Any]:
        """キャンバス付きプロジェクトを作成"""
        try:
            # キャンバスデータの検証
            validated_canvas = self._validate_canvas_data(canvas_data)
            
            # プロジェクト作成
            result = await self.project_crud.create_project(
                user_id=user_id,
                project_name=project_name,
                canvas_data=validated_canvas,
                update_comment=update_comment
            )
            
            return result
            
        except Exception as e:
            logger.error(f"キャンバス付きプロジェクト作成エラー: {e}")
            return {"success": False, "message": f"プロジェクト作成に失敗しました: {str(e)}"}
    
    async def auto_generate_canvas(self, idea_description: str, target_audience: Optional[str] = None,
                                 industry: Optional[str] = None) -> Dict[str, Any]:
        """AIによるキャンバス自動生成"""
        try:
            # RAGサービスでキャンバスを生成
            result = await self.rag_service.generate_canvas_from_idea(
                idea_description=idea_description,
                target_audience=target_audience,
                industry=industry
            )
            
            if not result["success"]:
                return result
            
            # 生成されたキャンバスデータを検証
            validated_canvas = self._validate_canvas_data(result["canvas_data"])
            
            return {
                "success": True,
                "canvas_data": validated_canvas,
                "raw_response": result.get("raw_response"),
                "message": "キャンバスが自動生成されました"
            }
            
        except Exception as e:
            logger.error(f"キャンバス自動生成エラー: {e}")
            return {"success": False, "message": f"キャンバス自動生成に失敗しました: {str(e)}"}
    
    async def update_project_canvas(self, project_id: int, user_id: int, canvas_data: Dict[str, Any],
                                  update_category: str = "manual", update_comment: Optional[str] = None) -> Dict[str, Any]:
        """プロジェクトキャンバスを更新"""
        try:
            # キャンバスデータの検証
            validated_canvas = self._validate_canvas_data(canvas_data)
            
            # プロジェクト更新
            result = await self.project_crud.update_project(
                project_id=project_id,
                user_id=user_id,
                canvas_data=validated_canvas,
                update_category=update_category,
                update_comment=update_comment
            )
            
            return result
            
        except Exception as e:
            logger.error(f"キャンバス更新エラー: {e}")
            return {"success": False, "message": f"キャンバス更新に失敗しました: {str(e)}"}
    
    async def research_and_enhance_canvas(self, project_id: int, user_id: int, 
                                        research_focus: Optional[str] = None) -> Dict[str, Any]:
        """リサーチに基づくキャンバス改善提案"""
        try:
            # 現在のキャンバスを取得
            current_project = await self.project_crud.get_project_latest(project_id, user_id)
            if not current_project:
                return {"success": False, "message": "プロジェクトが見つかりません"}
            
            current_canvas = current_project["canvas_data"]
            
            # RAGサービスで改善提案を生成
            enhancement_result = await self.rag_service.research_and_enhance_canvas(
                current_canvas=current_canvas,
                project_id=project_id,
                research_focus=research_focus
            )
            
            if not enhancement_result["success"]:
                return enhancement_result
            
            # 提案内容を整形
            return {
                "success": True,
                "current_canvas": current_canvas,
                "proposed_changes": enhancement_result["proposed_changes"],
                "source_summary": enhancement_result["source_summary"],
                "research_queries": enhancement_result["research_queries"],
                "message": "リサーチに基づく改善提案が生成されました"
            }
            
        except Exception as e:
            logger.error(f"キャンバス改善提案エラー: {e}")
            return {"success": False, "message": f"改善提案生成に失敗しました: {str(e)}"}
    
    async def analyze_interview_for_canvas(self, project_id: int, user_id: int, 
                                         interview_text: str) -> Dict[str, Any]:
        """インタビュー内容をキャンバスに反映するための分析"""
        try:
            # 現在のキャンバスを取得
            current_project = await self.project_crud.get_project_latest(project_id, user_id)
            if not current_project:
                return {"success": False, "message": "プロジェクトが見つかりません"}
            
            current_canvas = current_project["canvas_data"]
            
            # インタビュー分析
            analysis_result = await self.rag_service.analyze_interview_insights(
                interview_text=interview_text,
                current_canvas=current_canvas
            )
            
            if not analysis_result["success"]:
                return analysis_result
            
            return {
                "success": True,
                "current_canvas": current_canvas,
                "insights": analysis_result["insights"],
                "raw_analysis": analysis_result["raw_analysis"],
                "message": "インタビュー分析が完了しました"
            }
            
        except Exception as e:
            logger.error(f"インタビューキャンバス分析エラー: {e}")
            return {"success": False, "message": f"インタビュー分析に失敗しました: {str(e)}"}
    
    async def compare_canvas_versions(self, project_id: int, user_id: int, 
                                    version1: int, version2: int) -> Dict[str, Any]:
        """キャンバスバージョン間の差分を比較"""
        try:
            # 編集履歴から両バージョンのedit_idを取得
            edit_history = await self.project_crud.get_edit_history(project_id, user_id)
            
            edit_id1 = None
            edit_id2 = None
            
            for history in edit_history:
                if history["version"] == version1:
                    edit_id1 = history["edit_id"]
                elif history["version"] == version2:
                    edit_id2 = history["edit_id"]
            
            if not edit_id1 or not edit_id2:
                return {"success": False, "message": "指定されたバージョンが見つかりません"}
            
            # バージョン比較
            comparison_result = await self.project_crud.compare_canvas_versions(
                project_id=project_id,
                edit_id1=edit_id1,
                edit_id2=edit_id2
            )
            
            if not comparison_result["success"]:
                return comparison_result
            
            # 差分を可視化
            formatted_differences = self._format_canvas_differences(comparison_result["differences"])
            
            return {
                "success": True,
                "version1_data": comparison_result["version1"],
                "version2_data": comparison_result["version2"],
                "differences": formatted_differences,
                "summary": self._generate_difference_summary(formatted_differences),
                "message": "バージョン比較が完了しました"
            }
            
        except Exception as e:
            logger.error(f"キャンバス比較エラー: {e}")
            return {"success": False, "message": f"バージョン比較に失敗しました: {str(e)}"}
    
    async def validate_canvas_completeness(self, canvas_data: Dict[str, Any]) -> Dict[str, Any]:
        """キャンバスの完成度を検証"""
        try:
            validation_result = {
                "total_fields": len(self.canvas_fields),
                "completed_fields": 0,
                "empty_fields": [],
                "field_completion": {},
                "completion_percentage": 0,
                "recommendations": []
            }
            
            for field in self.canvas_fields:
                value = canvas_data.get(field, "")
                if value and value.strip():
                    validation_result["completed_fields"] += 1
                    validation_result["field_completion"][field] = {
                        "completed": True,
                        "length": len(value),
                        "quality_score": self._assess_field_quality(field, value)
                    }
                else:
                    validation_result["empty_fields"].append(field)
                    validation_result["field_completion"][field] = {
                        "completed": False,
                        "length": 0,
                        "quality_score": 0
                    }
            
            # 完成度計算
            validation_result["completion_percentage"] = round(
                (validation_result["completed_fields"] / validation_result["total_fields"]) * 100, 1
            )
            
            # 推奨事項生成
            validation_result["recommendations"] = self._generate_completion_recommendations(validation_result)
            
            return {
                "success": True,
                "validation": validation_result,
                "message": "キャンバス完成度検証が完了しました"
            }
            
        except Exception as e:
            logger.error(f"キャンバス検証エラー: {e}")
            return {"success": False, "message": f"キャンバス検証に失敗しました: {str(e)}"}
    
    def _validate_canvas_data(self, canvas_data: Dict[str, Any]) -> Dict[str, Any]:
        """キャンバスデータの検証と正規化"""
        validated_data = {}
        
        for field in self.canvas_fields:
            value = canvas_data.get(field, "")
            if isinstance(value, str):
                # 文字列の正規化
                validated_data[field] = value.strip()
            else:
                # 文字列以外の場合は文字列に変換
                validated_data[field] = str(value).strip() if value is not None else ""
        
        return validated_data
    
    def _format_canvas_differences(self, differences: Dict[str, Any]) -> Dict[str, Any]:
        """キャンバス差分の整形"""
        formatted = {}
        
        for field, diff_data in differences.items():
            field_label = self.field_labels.get(field, field)
            formatted[field] = {
                "field_label": field_label,
                "changed": diff_data["changed"],
                "version1": diff_data["version1"],
                "version2": diff_data["version2"],
                "change_type": self._classify_change_type(diff_data)
            }
        
        return formatted
    
    def _classify_change_type(self, diff_data: Dict[str, Any]) -> str:
        """変更タイプの分類"""
        val1 = diff_data["version1"]
        val2 = diff_data["version2"]
        
        if not val1 and val2:
            return "added"
        elif val1 and not val2:
            return "removed"
        elif val1 != val2:
            return "modified"
        else:
            return "unchanged"
    
    def _generate_difference_summary(self, differences: Dict[str, Any]) -> Dict[str, Any]:
        """差分サマリーの生成"""
        summary = {
            "total_fields": len(differences),
            "changed_fields": 0,
            "added_fields": 0,
            "removed_fields": 0,
            "modified_fields": 0,
            "unchanged_fields": 0
        }
        
        for field, diff_data in differences.items():
            change_type = diff_data["change_type"]
            if change_type == "added":
                summary["added_fields"] += 1
                summary["changed_fields"] += 1
            elif change_type == "removed":
                summary["removed_fields"] += 1
                summary["changed_fields"] += 1
            elif change_type == "modified":
                summary["modified_fields"] += 1
                summary["changed_fields"] += 1
            else:
                summary["unchanged_fields"] += 1
        
        return summary
    
    def _assess_field_quality(self, field: str, value: str) -> float:
        """フィールドの品質スコア評価（簡易版）"""
        if not value or not value.strip():
            return 0.0
        
        length = len(value.strip())
        
        # 長さに基づく基本スコア
        if length < 10:
            base_score = 0.3
        elif length < 50:
            base_score = 0.6
        elif length < 200:
            base_score = 0.8
        else:
            base_score = 1.0
        
        # 内容の具体性チェック（簡易）
        concrete_keywords = ["具体的", "〜円", "〜%", "〜人", "〜件", "〜回"]
        specificity_bonus = sum(0.1 for keyword in concrete_keywords if keyword in value)
        
        return min(base_score + specificity_bonus, 1.0)
    
    def _generate_completion_recommendations(self, validation_result: Dict[str, Any]) -> List[str]:
        """完成度に基づく推奨事項生成"""
        recommendations = []
        
        completion_pct = validation_result["completion_percentage"]
        
        if completion_pct < 50:
            recommendations.append("基本項目（課題、顧客セグメント、価値提案）の記入を優先してください")
        elif completion_pct < 80:
            recommendations.append("収益モデルとコスト構造の詳細化を検討してください")
        
        # 空フィールドの推奨
        empty_fields = validation_result["empty_fields"]
        if "problem" in empty_fields:
            recommendations.append("解決すべき課題を明確に定義してください")
        if "unique_value_proposition" in empty_fields:
            recommendations.append("競合との差別化要因を明確にしてください")
        
        # 品質向上の推奨
        low_quality_fields = [
            field for field, data in validation_result["field_completion"].items()
            if data["completed"] and data["quality_score"] < 0.5
        ]
        
        if low_quality_fields:
            recommendations.append("より具体的で詳細な内容の記入を検討してください")
        
        return recommendations