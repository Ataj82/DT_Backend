import asyncio
import logging
import uuid
from uuid import UUID
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from app.core.database import async_session, engine, Base
from app.core.security import get_password_hash
from app.features.users.models import User
from app.features.auth.models import UserSession
from app.features.lessons.models import Lesson, LessonMember, LessonBotChat
from app.features.chat.models import Chat, Message


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")

TEACHER_UUID = UUID("10000000-0000-4000-8000-000000000001")
STUDENT_UUID = UUID("10000000-0000-4000-8000-000000000002")
ADMIN_UUID = UUID("10000000-0000-4000-8000-000000000003")

OS_COURSE_UUID = UUID("c0000000-0000-4000-8000-000000000001")

STUDENT_ROSTER = [
    {"num_id": 100, "name": "انیس کریمی", "status": "online"},
    {"num_id": 101, "name": "زهرا ملایی", "status": "Last seen recently"},
    {"num_id": 102, "name": "محمد محمدی", "status": "online"},
    {"num_id": 103, "name": "سارا امینی", "status": "online"},
    {"num_id": 104, "name": "کیانا عباسی", "status": "online"},
    {"num_id": 105, "name": "علیرضا رضایی", "status": "online"},
    {"num_id": 106, "name": "فاطمه حسینی", "status": "online"},
    {"num_id": 107, "name": "امیرحسین مرادی", "status": "offline"},
    {"num_id": 108, "name": "مریم جعفری", "status": "online"},
    {"num_id": 109, "name": "حسین باقری", "status": "offline"},
    {"num_id": 110, "name": "نرگس موسوی", "status": "online"},
    {"num_id": 111, "name": "مهدی کاظمی", "status": "offline"},
    {"num_id": 112, "name": "رویا اکبری", "status": "online"},
    {"num_id": 113, "name": "رضا قاسمی", "status": "offline"},
    {"num_id": 114, "name": "زینب دهقان", "status": "online"},
    {"num_id": 115, "name": "سینا رستمی", "status": "offline"},
]

def student_uuid_from_num(num_id: int) -> UUID:
    return UUID(f"20000000-0000-4000-8000-{num_id:012d}")

async def seed_database():
    async with async_session() as session:
        # 1. Check if teacher user exists
        stmt = select(User).where(User.username == "teacher")
        result = await session.execute(stmt)
        teacher = result.scalar_one_or_none()

        if not teacher:
            logger.info("Creating default role accounts...")
            teacher = User(
                user_id=TEACHER_UUID,
                username="teacher",
                hashed_password=get_password_hash("teacher123"),
                first_name="استاد",
                last_name="دیجیتال",
                user_type="TEACHER",
                is_active=True,
                is_deleted=False,
            )
            student = User(
                user_id=STUDENT_UUID,
                username="student",
                hashed_password=get_password_hash("student123"),
                first_name="دانشجو",
                last_name="نمونه",
                user_type="STUDENT",
                is_active=True,
                is_deleted=False,
            )
            admin = User(
                user_id=ADMIN_UUID,
                username="admin",
                hashed_password=get_password_hash("admin123"),
                first_name="مدیر",
                last_name="سامانه",
                user_type="ADMIN",
                is_active=True,
                is_deleted=False,
            )
            session.add_all([teacher, student, admin])
            await session.flush()
        else:
            logger.info("Default role accounts already exist.")

        # 2. Seed Persian Courses
        stmt = select(Lesson).where(Lesson.lesson_id == OS_COURSE_UUID)
        result = await session.execute(stmt)
        os_lesson = result.scalar_one_or_none()

        if not os_lesson:
            logger.info("Creating Persian courses with UUIDs...")
            courses = [
                Lesson(
                    lesson_id=OS_COURSE_UUID,
                    title="سیستم عامل",
                    subject="سیستم عامل",
                    description="مطالعه مفاهیم و الگوریتم‌های مدیریت منابع سخت‌افزاری و نرم‌افزاری (هسته، حافظه، پردازش، ورودی/خروجی، فایل‌سیستم و زمان‌بندی)",
                    teacher_id=TEACHER_UUID,
                    is_active=True,
                    is_public=False,
                ),
            ]
            session.add_all(courses)
            await session.flush()
        else:
            logger.info("Course already seeded.")

        # 3. Seed Students Roster with UUIDs
        logger.info("Seeding students roster with Persian names and UUIDs...")
        for item in STUDENT_ROSTER:
            st_uuid = student_uuid_from_num(item["num_id"])
            username = "alireza_rezaei" if item["num_id"] == 105 else f"student_{item['num_id']}"
            parts = item["name"].split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ""

            stmt = select(User).where(User.user_id == st_uuid)
            res = await session.execute(stmt)
            existing_st = res.scalar_one_or_none()

            if not existing_st:
                new_st = User(
                    user_id=st_uuid,
                    username=username,
                    hashed_password=get_password_hash("password123"),
                    first_name=first_name,
                    last_name=last_name,
                    bio=f"دانشجوی درس سیستم عامل - وضعیت: {item['status']}",
                    user_type="STUDENT",
                    is_active=True,
                    is_deleted=False,
                )
                session.add(new_st)
                await session.flush()

            # Enroll in OS lesson
            stmt_mem = select(LessonMember).where(
                LessonMember.lesson_id == OS_COURSE_UUID,
                LessonMember.user_id == st_uuid
            )
            res_mem = await session.execute(stmt_mem)
            if not res_mem.scalar_one_or_none():
                member = LessonMember(
                    lesson_id=OS_COURSE_UUID,
                    user_id=st_uuid,
                    role="STUDENT",
                )
                session.add(member)

            # Seed realistic student user_sessions
            stmt_sess = select(UserSession).where(UserSession.user_id == st_uuid)
            res_sess = await session.execute(stmt_sess)
            if not res_sess.scalar_one_or_none():
                now = datetime.now(timezone.utc)
                if item.get("status") == "online":
                    last_act = now - timedelta(minutes=1 + (item["num_id"] % 3))
                elif "recently" in item.get("status", ""):
                    last_act = now - timedelta(hours=3 + (item["num_id"] % 5))
                else:
                    last_act = now - timedelta(hours=10 + (item["num_id"] % 18))

                import secrets
                st_sess = UserSession(
                    user_session_id=uuid.uuid4(),
                    user_id=st_uuid,
                    refresh_token_hash=secrets.token_hex(32),
                    device_name="Mobile Browser",
                    device_type="mobile",
                    is_mobile=True,
                    created_at=last_act - timedelta(days=7),
                    last_active_at=last_act,
                    expires_at=now + timedelta(days=30),
                )
                session.add(st_sess)

        # 4. Seed Course Chat and Initial Welcome Message
        stmt_chat = select(Chat).where(Chat.chat_id == OS_COURSE_UUID)
        res_chat = await session.execute(stmt_chat)
        course_chat = res_chat.scalar_one_or_none()

        if not course_chat:
            logger.info("Seeding course chat session...")
            course_chat = Chat(
                chat_id=OS_COURSE_UUID,
                chat_type="COURSE",
                title="سیستم عامل",
                description="کانال و چت هوشمند درس سیستم عامل",
                owner_id=TEACHER_UUID,
                is_public=False,
            )
            session.add(course_chat)
            await session.flush()

            welcome_msg = Message(
                chat_id=OS_COURSE_UUID,
                sender_id=TEACHER_UUID,
                content_type="TEXT",
                text_content="سلام! به سامانه گفت‌وگوی درس سیستم عامل خوش آمدید. هرگونه سوال در خصوص زمان‌بندی فرآیندها، مدیریت حافظه یا هماهنگی کلاس را می‌توانید در اینجا مطرح کنید.",
            )
            session.add(welcome_msg)

        await session.commit()
        logger.info("Database seeding completed successfully.")

if __name__ == "__main__":
    asyncio.run(seed_database())
