# app/features/lessons/rag_service.py
import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID

from app.features.lessons.models import LessonMaterial

logger = logging.getLogger("rag_service")

class LessonMaterialRAGService:
    """
    Modular service to connect lesson course materials with the RAG pipeline.
    Connects to the vector database or language model API configured via RAG_API_URL.
    """

    def __init__(self):
        self.rag_api_url = os.getenv("RAG_API_URL", "").strip()
        self.rag_api_key = os.getenv("RAG_API_KEY", "").strip()
        self.timeout_seconds = int(float(os.getenv("RAG_TIMEOUT_SECONDS", "30")))

    @property
    def is_configured(self) -> bool:
        return bool(self.rag_api_url)

    async def sync_material(
        self,
        material: LessonMaterial,
        file_path: Optional[str] = None,
        file_name: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Synchronize a course document with the RAG indexing pipeline.
        """
        now_str = datetime.now(timezone.utc).isoformat()

        if self.is_configured:
            try:
                import httpx
                headers = {"Authorization": f"Bearer {self.rag_api_key}"} if self.rag_api_key else {}
                payload = {
                    "material_id": str(material.material_id),
                    "lesson_id": str(material.lesson_id),
                    "title": material.title,
                    "description": material.description or "",
                    "file_name": file_name or "",
                    "mime_type": mime_type or "",
                }

                if file_path and os.path.isfile(file_path):
                    with open(file_path, "rb") as f:
                        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                            resp = await client.post(
                                f"{self.rag_api_url}/index",
                                data=payload,
                                files={"file": (file_name or "document", f, mime_type or "application/octet-stream")},
                                headers=headers,
                            )
                            resp.raise_for_status()
                            rag_res = resp.json()
                else:
                    async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                        resp = await client.post(
                            f"{self.rag_api_url}/index",
                            json=payload,
                            headers=headers,
                        )
                        resp.raise_for_status()
                        rag_res = resp.json()

                result = {
                    "status": "indexed",
                    "message": "جزوه با موفقیت در موتور جستجوی هوش مصنوعی (RAG) نمایه شد.",
                    "rag_metadata": {
                        **rag_res,
                        "last_synced_at": now_str,
                        "api_url": self.rag_api_url,
                    }
                }
                return result

            except Exception as exc:
                logger.error(f"Error syncing material {material.material_id} to RAG: {exc}")
                return {
                    "status": "failed",
                    "message": f"خطا در ارتباط با وب‌سرویس RAG: {str(exc)}",
                    "rag_metadata": {
                        "error": str(exc),
                        "failed_at": now_str,
                    }
                }

        # If external API is not configured, register status as ready
        return {
            "status": "ready",
            "message": "بستر ارتباطی RAG کاملاً فعال و آماده است.",
            "rag_metadata": {
                "bester_status": "ready_for_rag",
                "is_ready": True,
                "file_name": file_name,
                "registered_at": now_str,
            }
        }

    def get_status_info(self, material: LessonMaterial) -> Dict[str, Any]:
        """
        Query status information of document RAG indexing.
        """
        status = material.rag_status or "ready"
        metadata = material.rag_metadata or {}
        
        return {
            "material_id": material.material_id,
            "status": status,
            "is_configured": self.is_configured,
            "message": metadata.get("message") or (
                "آماده اتصال به هوش مصنوعی (RAG)" if status == "ready" else "در حال پردازش یا نمایه شده"
            ),
            "rag_metadata": metadata,
        }

rag_service = LessonMaterialRAGService()
