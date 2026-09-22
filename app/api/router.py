from fastapi import APIRouter
from app.features.users.router import router as users_router
from app.features.chat.router import router as chat_router
from app.features.auth.router import router as auth_router
from app.features.lessons.router import router as lesson_router
from app.features.courses.router import router as courses_router
from app.features.students.router import router as students_router
from app.features.navigation.router import router as navigation_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_router.include_router(users_router, prefix="/users", tags=["Users"])
api_router.include_router(courses_router, prefix="/courses", tags=["Courses"])
api_router.include_router(students_router, tags=["Students"])
api_router.include_router(navigation_router, prefix="/navigation", tags=["Navigation"])
api_router.include_router(chat_router, prefix="/chats", tags=["Chats"])
api_router.include_router(lesson_router, prefix="/lessons", tags=["Lessons"])
