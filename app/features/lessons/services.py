# app/features/lessons/service.py
import uuid
from uuid import UUID
from typing import List, Optional

import os
from pathlib import Path
from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.lessons.repository import LessonRepository
from app.features.lessons.schemas import *
from app.features.lessons.models import LessonMaterial
from app.features.lessons.rag_service import rag_service
from app.features.chat.repository import ChatRepository
from app.features.users.repository import UserRepository
from app.features.chat.models import Chat, ChatMember, ChatUserState, ChatMemberPermission, MessageAttachment
from app.features.chat.services import ChatService


class LessonService:
    def __init__(self, db:AsyncSession):
        self.db = db
        self.repo = LessonRepository(db)
        self.chat_repo = ChatRepository(db)
        self.user_repo = UserRepository(db)
        self.chat_service = ChatService(db)

    async def create_lesson(self, teacher_id: UUID, payload: LessonCreate) -> LessonResponse:
        bot_username = f"bot_{uuid.uuid4().hex[:8]}"
        bot_user = await self.user_repo.create(
            username=bot_username,
            # email=f"{bot_username}@bot.local",
            hashed_password="",
            first_name=f"Lesson Bot -",
            last_name= f"{payload.title}",
            user_type="bot"
        )

        lesson = await self.repo.create(
            teacher_id=teacher_id,
            bot_user_id=bot_user.user_id,
            **payload.model_dump(exclude_unset=True)
        )

        await self.repo.add_member(lesson.lesson_id, teacher_id, role="TEACHER")

        return LessonResponse.model_validate(lesson)
    async def get_lessons(self, user_id:UUID) -> List[LessonResponse]:
        lessons = await self.repo.get_lesson_member(user_id)
        return [LessonResponse.model_validate(l) for l in lessons]

    async def get_teacher_lessons(self, teacher_id: UUID) -> List[LessonResponse]:
        lessons = await self.repo.get_teacher_lessons(teacher_id)
        return [LessonResponse.model_validate(l) for l in lessons]

    async def get_members(self, lesson_id: UUID) -> List[LessonMemberResponse]:
        members = await self.repo.get_members(lesson_id)
        return [LessonMemberResponse.model_validate(m) for m in members]

    async def add_members(self, lesson_id: UUID, payload: LessonAddMembersRequest) -> List[LessonMemberResponse]:
        lesson = await self.repo.get_lesson(lesson_id)

        if not lesson.bot_user_id:
            raise HTTPException(status_code=500, detail="Lesson bot not configured")

        for user_id in payload.user_ids:
            existing = await self.repo.get_member(lesson_id, user_id)

            if not existing:
                await self.repo.add_member(lesson_id, user_id, role="STUDENT")

                await self._create_bot_chat_for_student(
                    lesson_id=lesson_id,
                    student_id=user_id,
                    bot_user_id=lesson.bot_user_id
                )

        return await self.get_members(lesson_id)

    def _map_material_response(self, m: LessonMaterial, lesson_id: UUID) -> LessonMaterialResponse:
        file_name = m.attachment.file_name if m.attachment else None
        file_size = m.attachment.file_size if m.attachment else None
        mime_type = m.attachment.mime_type if m.attachment else None
        download_url = f"/lessons/{lesson_id}/materials/{m.material_id}/download"

        return LessonMaterialResponse(
            material_id=m.material_id,
            title=m.title,
            description=m.description,
            attachment_id=m.attachment_id,
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            download_url=download_url,
            rag_status=m.rag_status or "ready",
            rag_metadata=m.rag_metadata or {},
            created_at=m.created_at,
        )

    async def upload_material(
        self,
        lesson_id: UUID,
        teacher_id: UUID,
        file: UploadFile,
        title: str,
        description: Optional[str] = None,
    ) -> LessonMaterialResponse:
        upload_dir = "uploads/materials"
        os.makedirs(upload_dir, exist_ok=True)

        ext = os.path.splitext(file.filename or "")[1]
        filename = f"{uuid.uuid4()}{ext}"
        storage_key = f"{upload_dir}/{filename}"

        content = await file.read()
        with open(storage_key, "wb") as f:
            f.write(content)

        attachment = MessageAttachment(
            message_id=None,
            chat_id=None,
            uploader_id=teacher_id,
            attachment_type="DOCUMENT",
            file_name=file.filename or filename,
            mime_type=file.content_type or "application/octet-stream",
            file_size=len(content),
            storage_key=storage_key,
            url=f"/{storage_key}",
        )
        await self.chat_repo.create_attachment(attachment)
        await self.db.commit()
        await self.db.refresh(attachment)

        clean_title = title.strip() if (title and title.strip()) else (file.filename or "جزوه درسی")
        clean_desc = description.strip() if (description and description.strip()) else None

        material = await self.repo.add_material(
            lesson_id=lesson_id,
            teacher_id=teacher_id,
            title=clean_title,
            description=clean_desc,
            attachment_id=attachment.attachment_id,
            rag_status="ready",
            rag_metadata={
                "is_ready": True,
                "bester_status": "ready_for_rag",
                "file_name": file.filename,
                "file_size": len(content),
            }
        )
        material.attachment = attachment
        return self._map_material_response(material, lesson_id)

    async def add_material(
        self, lesson_id: UUID, teacher_id: UUID, payload: LessonMaterialCreate
    ) -> LessonMaterialResponse:
        material = await self.repo.add_material(
            lesson_id=lesson_id,
            teacher_id=teacher_id,
            **payload.model_dump()
        )
        # Load full material with attachment
        full_material = await self.repo.get_material(lesson_id, material.material_id)
        return self._map_material_response(full_material or material, lesson_id)

    async def get_materials(self, lesson_id: UUID) -> List[LessonMaterialResponse]:
        materials = await self.repo.get_materials(lesson_id)
        return [self._map_material_response(m, lesson_id) for m in materials]

    async def get_material_file(self, lesson_id: UUID, material_id: UUID):
        material = await self.repo.get_material(lesson_id, material_id)
        if not material:
            raise HTTPException(status_code=404, detail="جزوه یافت نشد")
        if not material.attachment:
            raise HTTPException(status_code=404, detail="فایل پیوست جزوه یافت نشد")

        file_path = Path(material.attachment.storage_key).resolve()
        if not file_path.is_file():
            fname = Path(material.attachment.storage_key).name
            fallback = (Path("uploads/materials") / fname).resolve()
            if fallback.is_file():
                file_path = fallback
            else:
                raise HTTPException(status_code=404, detail="فایل روی سرور موجود نیست")

        return file_path, material.attachment.file_name or "material", material.attachment.mime_type or "application/octet-stream"

    async def delete_material(self, lesson_id: UUID, material_id: UUID, teacher_id: UUID):
        material = await self.repo.get_material(lesson_id, material_id)
        if not material:
            raise HTTPException(status_code=404, detail="جزوه یافت نشد")
        if material.teacher_id != teacher_id:
            raise HTTPException(status_code=403, detail="فقط استاد ایجادکننده جزوه دسترسی حذف دارد")

        await self.repo.delete_material(material)
        return {"status": "success", "message": "جزوه با موفقیت حذف شد"}

    async def sync_material_rag(self, lesson_id: UUID, material_id: UUID, teacher_id: UUID) -> LessonMaterialRagSyncResponse:
        material = await self.repo.get_material(lesson_id, material_id)
        if not material:
            raise HTTPException(status_code=404, detail="جزوه یافت نشد")

        file_path = None
        file_name = None
        mime_type = None
        if material.attachment:
            file_name = material.attachment.file_name
            mime_type = material.attachment.mime_type
            clean_filename = Path(material.attachment.storage_key).name
            candidate = (Path("uploads/materials") / clean_filename).resolve()
            if candidate.is_file():
                file_path = str(candidate)

        result = await rag_service.sync_material(
            material=material,
            file_path=file_path,
            file_name=file_name,
            mime_type=mime_type,
        )
        material.rag_status = result.get("status", "ready")
        material.rag_metadata = result.get("rag_metadata", {})
        await self.repo.update_material(material)

        return LessonMaterialRagSyncResponse(
            material_id=material.material_id,
            status=material.rag_status,
            message=result.get("message", "وضعیت همگام‌سازی بروزرسانی شد"),
            rag_metadata=material.rag_metadata,
        )

    async def get_rag_status(self, lesson_id: UUID, material_id: UUID):
        material = await self.repo.get_material(lesson_id, material_id)
        if not material:
            raise HTTPException(status_code=404, detail="جزوه یافت نشد")
        return rag_service.get_status_info(material)

    async def create_quiz(
        self, lesson_id: UUID, teacher_id: UUID, payload: LessonQuizCreate
    ) -> LessonQuizResponse:
        data = payload.model_dump(exclude_unset=True)
        if "student_ids" in data and data["student_ids"]:
            data["student_ids"] = [str(sid) for sid in data["student_ids"]]

        from datetime import datetime as dt, timezone, timedelta
        tehran_tz = timezone(timedelta(hours=3, minutes=30))

        def _parse_time_val(val):
            if not val:
                return None
            if isinstance(val, dt):
                return val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)
            s = str(val).strip()
            # ISO timestamp string
            try:
                res = dt.fromisoformat(s.replace("Z", "+00:00"))
                if res.tzinfo is None:
                    res = res.replace(tzinfo=timezone.utc)
                return res
            except Exception:
                pass
            # HH:MM local clock string
            try:
                t = dt.strptime(s, "%H:%M").time()
                local_now = dt.now(tehran_tz)
                local_dt = dt.combine(local_now.date(), t, tzinfo=tehran_tz)
                return local_dt.astimezone(timezone.utc)
            except Exception:
                return None

        if "start_at" in data:
            data["start_at"] = _parse_time_val(data["start_at"])
        if "end_at" in data:
            data["end_at"] = _parse_time_val(data["end_at"])

        materials = data.pop("materials", None)

        quiz = await self.repo.create_quiz(
            lesson_id=lesson_id,
            teacher_id=teacher_id,
            **data
        )

        # Auto-sync with Adaptive Exam Pipeline
        try:
            from app.features.exam_pipeline.goals.models import GoalModel
            from app.features.exam_pipeline.api.dependencies import get_framework
            from app.features.exam_pipeline.multiuser.models import User as PipelineUser, UserRole as PipelineUserRole

            fw = get_framework()
            mu_svc = fw.services.multi_user_service

            prof = mu_svc.repository.get_user(str(teacher_id))
            if not prof:
                prof = PipelineUser(
                    id=str(teacher_id),
                    email=f"teacher_{teacher_id}@dt.internal",
                    display_name="Teacher",
                    password_hash="",
                    role=PipelineUserRole.PROFESSOR,
                )
                mu_svc.repository.save_user(prof)

            from app.features.exam_pipeline.knowledge.models import KnowledgeBase

            kb_id = f"kb_{lesson_id}"
            kb = fw.services.knowledge_service.get_knowledge_base(kb_id)
            if not kb:
                kb = KnowledgeBase(
                    id=kb_id,
                    title=f"Knowledge Base: {quiz.title}",
                    description=quiz.description or "",
                )
                fw.services.knowledge_service.save(kb)

            goals_list = data.get("goals") or [f"مباحث آزمون {quiz.title}"]
            dur_mins = data.get("duration_minutes") or 15
            goal_model = GoalModel.create_from_input(
                knowledge_base_id=kb_id,
                goals_data=goals_list,
                title=quiz.title,
                course_id=str(lesson_id),
                lesson_id=str(lesson_id),
                total_duration_minutes=dur_mins,
            )
            fw.services.goal_service.save(goal_model)
            allocations = goal_model.calculate_time_allocations(dur_mins * 60)

            gap_m = data.get("gap_minutes") or 5
            assignment = mu_svc.create_assignment(
                professor=prof,
                title=quiz.title,
                description=quiz.description or f"آزمون درس {quiz.title}",
                knowledge_base_id=kb_id,
                goal_model_id=goal_model.id,
                duration_seconds=dur_mins * 60,
                goal_time_allocations_seconds=allocations,
                passing_threshold=0.70,
                allow_followup_questions=True,
                starts_at=quiz.start_at,
                ends_at=quiz.end_at,
                assignment_id=str(quiz.quiz_id),
            )

            if assignment.configuration_snapshot is None:
                assignment.configuration_snapshot = {}
            assignment.configuration_snapshot["gap_minutes"] = gap_m
            if materials:
                assignment.configuration_snapshot["materials"] = materials

            student_ids = data.get("student_ids") or []
            cleaned_student_ids = []
            if student_ids:
                cleaned_student_ids = [str(s).strip() for s in student_ids if str(s).strip()]
                for sid in cleaned_student_ids:
                    existing_st = mu_svc.repository.get_user(sid)
                    if not existing_st or existing_st.role != PipelineUserRole.STUDENT:
                        mu_svc.repository.save_user(
                            PipelineUser(
                                id=sid,
                                email=f"{sid}@dt.internal",
                                display_name=f"Student {sid}",
                                password_hash="",
                                role=PipelineUserRole.STUDENT,
                            )
                        )
                try:
                    mu_svc.enroll_students(
                        professor=prof,
                        assignment_id=assignment.id,
                        student_ids=cleaned_student_ids,
                    )
                except Exception as enroll_err:
                    import logging
                    logging.getLogger(__name__).warning("Enroll warning in lesson quiz sync: %s", enroll_err)

                # Pre-assign initial time slots
                try:
                    from app.features.exam_pipeline.api.routers.exam_requests import _generate_time_slots
                    _, _, init_slots = _generate_time_slots(
                        assignment.starts_at,
                        assignment.ends_at,
                        duration_minutes=dur_mins,
                        gap_minutes=gap_m,
                    )
                    student_slots = {}
                    for i, sid in enumerate(cleaned_student_ids):
                        if i < len(init_slots):
                            student_slots[sid] = {
                                "slot_index": init_slots[i].slot_index,
                                "start_time": init_slots[i].start_time,
                                "end_time": init_slots[i].end_time,
                            }
                    assignment.configuration_snapshot["student_slots"] = student_slots
                    mu_svc.repository.save_assignment(assignment)
                except Exception as slot_err:
                    import logging
                    logging.getLogger(__name__).warning("Initial slots generation error: %s", slot_err)

            mu_svc.publish_assignment(professor=prof, assignment_id=assignment.id)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Adaptive exam pipeline sync error: %s", e)

        return LessonQuizResponse.model_validate(quiz)

    async def _create_bot_chat_for_student(
        self,
        lesson_id: uuid.UUID,
        student_id: uuid.UUID,
        bot_user_id: uuid.UUID
    ):
        chat_service = ChatService(self.db)

        try:
            # Create private chat between student and bot
            chat = await chat_service.create_chat(
                actor_id=student_id,
                chat_type="PRIVATE",
                user_ids=[bot_user_id],
                title="Lesson Assistant",
                description=None,
                avatar_url=None,
                is_public=False,
                username=None,
            )

            # Persist lesson-bot_chat association
            bot_chat = await self.repo.create_bot_chat(
                lesson_id=lesson_id,
                student_id=student_id,
                chat_id=chat.chat_id
            )

            await self.db.commit()
            return bot_chat

        except Exception:
            await self.db.rollback()
            raise


    async def get_bot_chat_for_student(
        self,
        lesson_id: uuid.UUID,
        student_id: uuid.UUID
    ) -> LessonBotChatResponse:

        # Step 1: Check if a bot chat already exists for this student and lesson
        bot_chat = await self.repo.get_bot_chat(lesson_id, student_id)

        lesson = await self.repo.get_lesson(lesson_id)
        if not lesson.bot_user_id:
            raise HTTPException(status_code=404, detail="Lesson bot not found")
        
        if bot_chat:
            setattr(bot_chat, 'bot_user_id', lesson.bot_user_id)
            return LessonBotChatResponse.model_validate(bot_chat) 

        # If not found, create new bot chat
        bot_chat = await self._create_bot_chat_for_student(
            lesson_id=lesson_id,
            student_id=student_id,
            bot_user_id=lesson.bot_user_id
        )
        return LessonBotChatResponse.model_validate(bot_chat)

    async def get_chat_detail_for_teacher(self,student_id:UUID,lesson_id:UUID):
        
        bot_chat = await self.repo.get_bot_chat(lesson_id, student_id)
        lesson = await self.repo.get_lesson(lesson_id=lesson_id)
        chat = await self.chat_service.get_chat_detail(chat_id=bot_chat.chat_id,user_id=lesson.bot_user_id)
        return chat


    async def get_user_chat_state_for_teacher(self,student_id:UUID,lesson_id:UUID):
        bot_chat = await self.repo.get_bot_chat(lesson_id, student_id)
        lesson = await self.repo.get_lesson(lesson_id=lesson_id)
        chat_state = await self.chat_service.get_user_chat_state(chat_id=bot_chat.chat_id, user_id=lesson.bot_user_id)
        return chat_state
    
    async def get_messages_for_teacher(
        self,
        lesson_id: UUID,
        chat_id: UUID,
        user_id: UUID,
        limit:int,
        before_message_id: Optional[uuid.UUID],
        after_message_id: Optional[uuid.UUID],
        around_message_id: Optional[uuid.UUID],
        include_deleted: bool,
        ):
        lesson = await self.repo.get_lesson(lesson_id=lesson_id)
        return await self.chat_service.get_messages(chat_id,lesson.bot_user_id,limit,before_message_id,after_message_id,around_message_id,include_deleted)

    async def send_message_for_teacher(
        self,
        lesson_id:UUID,
        chat_id: UUID,
        sender_id: UUID,
        client_message_id: Optional[str],
        content_type: str,
        text_content: Optional[str],
        metadata_json: Optional[dict],
        reply_to_message_id: Optional[UUID],
        attachment_ids: List[UUID],
        is_silent: bool,
        scheduled_at: Optional[datetime],
    ):
        lesson = await self.repo.get_lesson(lesson_id=lesson_id)
        return await self.chat_service.send_message(chat_id= chat_id,sender_id=lesson.bot_user_id, client_message_id=client_message_id,content_type=content_type, text_content=text_content, metadata_json=metadata_json,reply_to_message_id=reply_to_message_id,attachment_ids=attachment_ids,is_silent=is_silent,scheduled_at=scheduled_at)



        



    async def get_quizzes(self, lesson_id: UUID) -> List[LessonQuizResponse]:
        quizzes = await self.repo.get_quizzes(lesson_id)
        return [LessonQuizResponse.model_validate(q) for q in quizzes]

    async def add_quiz_question(self, quiz_id: UUID, payload: QuizQuestionCreate) -> QuizQuestionResponse:
        question = await self.repo.create_quiz_question(quiz_id=quiz_id, **payload.model_dump(exclude={"options"}), options=payload.options)
        return QuizQuestionResponse.model_validate(question)

    async def get_quiz_questions(self, quiz_id: UUID) -> List[QuizQuestionResponse]:
        questions = await self.repo.get_quiz_questions(quiz_id)
        return [QuizQuestionResponse.model_validate(q) for q in questions]

    async def get_quiz_attempts(self, quiz_id: UUID) -> List[QuizAttemptListResponse]:
        attempts = await self.repo.get_quiz_attempts(quiz_id)
        return [QuizAttemptListResponse.model_validate(a) for a in attempts]
