"""
Vector Database Abstraction & Multi-Tier Persistent Storage for Biometric Profiles.
Production Stack Architecture:
  1. L1 Cache: High-speed in-process memory dictionaries
  2. L2 Cache & Real-Time Buffering: Redis (session frame buffering, TTL expiry, distributed state)
  3. Persistent Storage: PostgreSQL (UserBiometricProfile via SQLAlchemy async engine)
"""

import os
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import sqlalchemy as sa
from sqlalchemy.future import select

from app.core.redis import get_redis
from .db_models import UserBiometricProfile


def _get_async_session():
    try:
        from app.core.database import async_session
        return async_session
    except Exception as e:
        return None

# L1 In-memory vector and profile cache
VECTOR_DATABASE: Dict[str, List[float]] = {}
STUDENT_PROFILES: Dict[str, Dict[str, Any]] = {}
_NEUTRAL_SESSIONS: Dict[str, List[List[float]]] = {}


# ============================================================================
# REDIS SESSION BUFFERING & REAL-TIME CACHE
# ============================================================================

async def buffer_neutral_sample(user_id: str, sample: List[float], ttl_seconds: int = 60) -> int:
    """
    Pushes a 7D neutral feature vector directly to the user's active Redis session buffer.
    Automatically expires after ttl_seconds if abandoned.
    """
    uid = user_id.strip()
    redis = get_redis()
    if redis:
        try:
            key = f"biometrics:neutral_session:{uid}"
            count = await redis.rpush(key, json.dumps(sample))
            await redis.expire(key, ttl_seconds)
            return count
        except Exception as e:
            print(f"[biometrics-redis] Buffer error, using memory fallback: {e}")

    # In-memory fallback
    if uid not in _NEUTRAL_SESSIONS:
        _NEUTRAL_SESSIONS[uid] = []
    _NEUTRAL_SESSIONS[uid].append(sample)
    return len(_NEUTRAL_SESSIONS[uid])


async def get_buffered_neutral_samples(user_id: str) -> List[List[float]]:
    """Retrieves all buffered neutral feature vectors from Redis or memory fallback."""
    uid = user_id.strip()
    redis = get_redis()
    samples: List[List[float]] = []

    if redis:
        try:
            key = f"biometrics:neutral_session:{uid}"
            raw_items = await redis.lrange(key, 0, -1)
            if raw_items:
                samples = [json.loads(item) for item in raw_items]
                return samples
        except Exception as e:
            print(f"[biometrics-redis] Failed to get neutral samples from redis: {e}")

    # Fallback to in-memory buffer
    return _NEUTRAL_SESSIONS.get(uid, [])


async def clear_buffered_neutral_samples(user_id: str) -> None:
    """Evicts the temporary calibration session buffer from Redis and memory."""
    uid = user_id.strip()
    redis = get_redis()
    if redis:
        try:
            await redis.delete(f"biometrics:neutral_session:{uid}")
        except Exception as e:
            print(f"[biometrics-redis] Error clearing neutral buffer: {e}")

    if uid in _NEUTRAL_SESSIONS:
        del _NEUTRAL_SESSIONS[uid]


async def cache_biometric_profile(user_id: str, profile_dict: Dict[str, Any]) -> None:
    """Caches student biometric status in Redis with a 2-hour TTL."""
    uid = user_id.strip()
    redis = get_redis()
    if redis:
        try:
            key = f"biometrics:profile:{uid}"
            await redis.set(key, json.dumps(profile_dict), ex=7200)
        except Exception as e:
            print(f"[biometrics-redis] Error caching profile: {e}")


async def get_cached_biometric_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetches cached student biometric profile from Redis."""
    uid = user_id.strip()
    redis = get_redis()
    if redis:
        try:
            key = f"biometrics:profile:{uid}"
            val = await redis.get(key)
            if val:
                return json.loads(val)
        except Exception as e:
            print(f"[biometrics-redis] Error reading cached profile: {e}")
    return None


# ============================================================================
# POSTGRESQL PERSISTENT STORAGE
# ============================================================================

async def persist_biometric_profile_db(user_id: str, **kwargs) -> Optional[UserBiometricProfile]:
    """
    Saves or updates the persistent biometric profile in PostgreSQL.
    """
    session_factory = _get_async_session()
    if not session_factory:
        return None
    uid = user_id.strip()
    try:
        async with session_factory() as session:
            stmt = select(UserBiometricProfile).where(UserBiometricProfile.user_id == uid)
            result = await session.execute(stmt)
            profile_obj = result.scalar_one_or_none()

            if profile_obj is None:
                profile_obj = UserBiometricProfile(user_id=uid)
                session.add(profile_obj)

            for key, val in kwargs.items():
                if hasattr(profile_obj, key):
                    setattr(profile_obj, key, val)

            profile_obj.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(profile_obj)
            return profile_obj
    except Exception as e:
        print(f"[biometrics-db] Warning: PostgreSQL profile persist error: {e}")
        return None


async def get_biometric_profile_db(user_id: str) -> Optional[UserBiometricProfile]:
    """Queries persistent biometric profile directly from PostgreSQL."""
    session_factory = _get_async_session()
    if not session_factory:
        return None
    uid = user_id.strip()
    try:
        async with session_factory() as session:
            stmt = select(UserBiometricProfile).where(UserBiometricProfile.user_id == uid)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    except Exception as e:
        print(f"[biometrics-db] Warning: PostgreSQL get profile error: {e}")
        return None


# ============================================================================
# HIGH-LEVEL PERSISTENCE & RESTORATION
# ============================================================================

async def save_face_embedding_async(user_id: str, embedding: List[float], liveness_mode: str = "genuine") -> None:
    """Persists face embedding to memory L1, Redis cache, and PostgreSQL."""
    uid = user_id.strip()
    VECTOR_DATABASE[uid] = embedding

    if uid not in STUDENT_PROFILES:
        STUDENT_PROFILES[uid] = {}
    STUDENT_PROFILES[uid]["is_enrolled"] = True
    STUDENT_PROFILES[uid]["enrolled_at"] = datetime.utcnow().isoformat()
    STUDENT_PROFILES[uid]["liveness"] = liveness_mode

    # Redis cache
    redis = get_redis()
    if redis:
        try:
            await redis.set(f"biometrics:face:{uid}", json.dumps(embedding), ex=86400 * 7)
        except Exception as e:
            print(f"[biometrics-redis] Error caching face embedding: {e}")

    # PostgreSQL persistent table
    await persist_biometric_profile_db(
        uid,
        is_enrolled=True,
        enrolled_at=datetime.utcnow(),
        face_embedding=embedding,
        liveness_status=liveness_mode
    )
    await cache_biometric_profile(uid, STUDENT_PROFILES[uid])


def save_face_embedding(user_id: str, embedding: List[float]) -> None:
    """Synchronous interface with background task dispatch."""
    uid = user_id.strip()
    VECTOR_DATABASE[uid] = embedding
    if uid not in STUDENT_PROFILES:
        STUDENT_PROFILES[uid] = {}
    STUDENT_PROFILES[uid]["is_enrolled"] = True

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(save_face_embedding_async(uid, embedding))
    except Exception:
        pass


async def save_neutral_baseline_async(
    user_id: str,
    mu: List[float],
    sigma: List[float],
    samples_count: int
) -> None:
    """Persists calibrated neutral baseline to PostgreSQL and Redis."""
    uid = user_id.strip()
    if uid not in STUDENT_PROFILES:
        STUDENT_PROFILES[uid] = {}
    STUDENT_PROFILES[uid]["is_neutral_calibrated"] = True
    STUDENT_PROFILES[uid]["neutral_calibrated_at"] = datetime.utcnow().isoformat()
    STUDENT_PROFILES[uid]["neutral_samples_count"] = samples_count

    # Cache baseline in Redis
    redis = get_redis()
    if redis:
        try:
            payload = {"mean": mu, "std": sigma}
            await redis.set(f"biometrics:neutral_baseline:{uid}", json.dumps(payload), ex=86400 * 7)
        except Exception as e:
            print(f"[biometrics-redis] Error caching neutral baseline: {e}")

    # Persist in PostgreSQL
    await persist_biometric_profile_db(
        uid,
        is_neutral_calibrated=True,
        neutral_calibrated_at=datetime.utcnow(),
        neutral_samples_count=samples_count,
        neutral_baseline_mean=mu,
        neutral_baseline_std=sigma
    )
    await cache_biometric_profile(uid, STUDENT_PROFILES[uid])


async def save_gaze_calibration_async(
    user_id: str,
    weights: List[List[float]],
    samples_count: int
) -> None:
    """Persists solved gaze regression weights to PostgreSQL and Redis."""
    uid = user_id.strip()
    if uid not in STUDENT_PROFILES:
        STUDENT_PROFILES[uid] = {}
    STUDENT_PROFILES[uid]["is_gaze_calibrated"] = True
    STUDENT_PROFILES[uid]["gaze_calibrated_at"] = datetime.utcnow().isoformat()
    STUDENT_PROFILES[uid]["gaze_samples_count"] = samples_count

    # Cache weights in Redis
    redis = get_redis()
    if redis:
        try:
            await redis.set(f"biometrics:gaze_weights:{uid}", json.dumps(weights), ex=86400 * 7)
        except Exception as e:
            print(f"[biometrics-redis] Error caching gaze weights: {e}")

    # Persist in PostgreSQL
    await persist_biometric_profile_db(
        uid,
        is_gaze_calibrated=True,
        gaze_calibrated_at=datetime.utcnow(),
        gaze_samples_count=samples_count,
        gaze_weights=weights
    )
    await cache_biometric_profile(uid, STUDENT_PROFILES[uid])


async def restore_user_calibration_state(user_id: str) -> None:
    """
    Hydrates in-memory affect and gaze engines from Redis or PostgreSQL if not already calibrated.
    Ensures zero state-loss across server restarts and worker scaling.
    """
    uid = user_id.strip()
    from .emotion_engine import get_affect_engine
    from .attention import get_user_calibrator

    affect_engine = get_affect_engine(uid)
    gaze_calibrator = get_user_calibrator(uid)

    # If both already primed in RAM, nothing to do
    if affect_engine.calibrator.is_calibrated and gaze_calibrator.is_calibrated:
        return

    # 1. Attempt Redis fast restore
    redis = get_redis()
    restored_neutral = False
    restored_gaze = False

    if redis:
        try:
            if not affect_engine.calibrator.is_calibrated:
                raw_neutral = await redis.get(f"biometrics:neutral_baseline:{uid}")
                if raw_neutral:
                    data = json.loads(raw_neutral)
                    affect_engine.load_persisted_baseline(data.get("mean"), data.get("std"))
                    restored_neutral = True

            if not gaze_calibrator.is_calibrated:
                raw_gaze = await redis.get(f"biometrics:gaze_weights:{uid}")
                if raw_gaze:
                    weights = json.loads(raw_gaze)
                    gaze_calibrator.load_persisted_weights(weights)
                    restored_gaze = True
        except Exception as e:
            print(f"[biometrics-redis] Redis restore error: {e}")

    # 2. PostgreSQL fallback restore if still unprimed
    if not (restored_neutral and restored_gaze):
        try:
            db_profile = await get_biometric_profile_db(uid)
            if db_profile:
                if not affect_engine.calibrator.is_calibrated and db_profile.is_neutral_calibrated:
                    if db_profile.neutral_baseline_mean and db_profile.neutral_baseline_std:
                        affect_engine.load_persisted_baseline(
                            db_profile.neutral_baseline_mean,
                            db_profile.neutral_baseline_std
                        )
                if not gaze_calibrator.is_calibrated and db_profile.is_gaze_calibrated:
                    if db_profile.gaze_weights:
                        gaze_calibrator.load_persisted_weights(
                            db_profile.gaze_weights,
                            samples_count=db_profile.gaze_samples_count or 5
                        )
                if uid not in VECTOR_DATABASE and db_profile.face_embedding:
                    VECTOR_DATABASE[uid] = db_profile.face_embedding
                STUDENT_PROFILES[uid] = db_profile.to_dict()
        except Exception as e:
            print(f"[biometrics-db] DB restore error: {e}")


def get_face_embedding(user_id: str) -> Optional[List[float]]:
    """Retrieves the 512-D embedding for a user if enrolled, else None."""
    return VECTOR_DATABASE.get(user_id.strip())


def delete_face_embedding(user_id: str) -> bool:
    """Deletes an enrolled user from memory and schedules persistent deletion."""
    uid = user_id.strip()
    if uid in VECTOR_DATABASE:
        del VECTOR_DATABASE[uid]
        if uid in STUDENT_PROFILES:
            STUDENT_PROFILES[uid]["is_enrolled"] = False

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(persist_biometric_profile_db(uid, is_enrolled=False, face_embedding=None))
        except Exception:
            pass
        return True
    return False


def list_enrolled_users() -> List[str]:
    return list(VECTOR_DATABASE.keys())


def get_enrolled_count() -> int:
    return len(VECTOR_DATABASE)


def update_student_profile(user_id: str, updates: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    uid = user_id.strip()
    if uid not in STUDENT_PROFILES:
        STUDENT_PROFILES[uid] = {
            "is_enrolled": uid in VECTOR_DATABASE,
            "is_gaze_calibrated": False,
            "is_neutral_calibrated": False
        }
    if updates:
        STUDENT_PROFILES[uid].update(updates)
    if kwargs:
        STUDENT_PROFILES[uid].update(kwargs)
    return STUDENT_PROFILES[uid]


def get_student_profile(user_id: str) -> Dict[str, Any]:
    uid = user_id.strip()
    profile = STUDENT_PROFILES.get(uid, {
        "is_enrolled": uid in VECTOR_DATABASE,
        "is_gaze_calibrated": False,
        "is_neutral_calibrated": False,
        "can_edit": True,
    })
    profile["is_enrolled"] = uid in VECTOR_DATABASE
    if "can_edit" not in profile:
        profile["can_edit"] = True
    return profile


async def reset_student_biometrics_db(user_id: str) -> bool:
    """
    Completely wipes a user's biometric data from memory, Redis cache, and PostgreSQL.
    """
    uid = user_id.strip()
    VECTOR_DATABASE.pop(uid, None)
    STUDENT_PROFILES.pop(uid, None)

    redis = get_redis()
    if redis:
        try:
            await redis.delete(
                f"biometrics:face:{uid}",
                f"biometrics:neutral_baseline:{uid}",
                f"biometrics:gaze_weights:{uid}",
                f"biometrics:neutral_session:{uid}",
                f"biometrics:profile:{uid}"
            )
        except Exception as e:
            print(f"[biometrics-redis] Error clearing user redis cache: {e}")

    await persist_biometric_profile_db(
        uid,
        is_enrolled=False,
        face_embedding=None,
        is_gaze_calibrated=False,
        gaze_weights=None,
        gaze_samples_count=0,
        is_neutral_calibrated=False,
        neutral_baseline_mean=None,
        neutral_baseline_std=None,
        neutral_samples_count=0
    )
    return True
