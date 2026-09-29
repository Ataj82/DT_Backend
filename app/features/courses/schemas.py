from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

class CourseResponse(BaseModel):
    id: UUID
    title: str
    titleFa: str
    titleEn: Optional[str] = None
    preview: str = ""
    previewEn: Optional[str] = "This course includes educational materials and related resources."
    description: Optional[str] = None
    descriptionEn: Optional[str] = "This course includes educational materials and related resources."
    accessLevel: Optional[str] = "private"
    photo_url: Optional[str] = None
    date: str
    unreadCount: int = 0
    teacher_name: Optional[str] = None
    instructor_name: Optional[str] = None
    isActive: bool = True
    is_active: bool = True
    is_enrolled: Optional[bool] = False
    has_pending_request: Optional[bool] = False
    degree: Optional[str] = "کارشناسی"
    units: Optional[int] = 3
    course_code: Optional[str] = None
    department: Optional[str] = "مهندسی کامپیوتر"
    term: Optional[str] = "نیم‌سال دوم ۱۴۰۴-۱۴۰۵"

class JoinCourseResponse(BaseModel):
    success: bool
    status: str  # "enrolled" | "pending"
    message: str
    course_id: UUID

class TeacherJoinRequestResponse(BaseModel):
    id: UUID
    student_id: UUID
    student_name: str
    student_username: Optional[str] = None
    student_avatar: Optional[str] = None
    course_id: UUID
    course_title: str
    requested_at: str
    status: str = "PENDING"

class StudentNotificationResponse(BaseModel):
    id: UUID
    title: str
    message: str
    course_id: UUID
    course_title: str
    course_avatar: Optional[str] = None
    date: str
    status: str = "APPROVED"
    type: str = "membership_approved"

class CourseDetailResponse(BaseModel):
    courseId: UUID
    name: str
    nameFa: str
    nameEn: Optional[str] = None
    teacher_name: Optional[str] = None
    instructor_name: Optional[str] = None
    startDate: Optional[str] = "2026-03-01"
    endDate: Optional[str] = "2026-07-01"
    description: Optional[str] = ""
    accessLevel: str = "private"
    photo_url: Optional[str] = None
    isActive: bool = True
    is_active: bool = True
    degree: Optional[str] = "کارشناسی"
    units: Optional[int] = 3
    course_code: Optional[str] = None
    department: Optional[str] = "مهندسی کامپیوتر"
    term: Optional[str] = "نیم‌سال دوم ۱۴۰۴-۱۴۰۵"

class CourseUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    accessLevel: Optional[str] = None
    isActive: Optional[bool] = None
    is_active: Optional[bool] = None

class CourseStatusUpdateRequest(BaseModel):
    isActive: Optional[bool] = None
    is_active: Optional[bool] = None

class CategoryItem(BaseModel):
    id: str
    name: str

class RecentCourseItem(BaseModel):
    id: UUID
    name: str
    visibility: str = "Private"

class CourseOverviewResponse(BaseModel):
    categories: List[CategoryItem]
    recentCourses: List[RecentCourseItem]
