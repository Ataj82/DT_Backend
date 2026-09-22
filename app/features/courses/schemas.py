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
    isActive: bool = True
    is_active: bool = True

class CourseDetailResponse(BaseModel):
    courseId: UUID
    name: str
    nameFa: str
    nameEn: Optional[str] = None
    startDate: Optional[str] = "2026-03-01"
    endDate: Optional[str] = "2026-07-01"
    description: Optional[str] = ""
    accessLevel: str = "private"
    photo_url: Optional[str] = None
    isActive: bool = True
    is_active: bool = True

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
