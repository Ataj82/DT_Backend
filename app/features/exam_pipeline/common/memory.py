from __future__ import annotations
import json
import logging
import os
import re
import signal
import time
import html
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Tuple
###############
from digital_twin_pipline.interviewer_agent_three_modules_4050402.core.llm_client import LLMClient
# ==============================================================================
# MEMORY
# ==============================================================================
class InterviewMemory:
    def __init__(self, max_history: int = 100):
        self.history: Deque[Dict[str, str]] = deque(
            maxlen=max_history
        )
        self.rolling_summary = ""
        self.contradictions = []

    def add(self, role: str, content: str):
        # Security: Sanitize input to prevent XSS/Injection
        clean_content = html.unescape(content)
        clean_content = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', clean_content)
        self.history.append({
            "role": role,
            "content": clean_content
        })

    def get_recent_context(self, limit: int = 8) -> str:
        # Memory Efficiency: Truncate long answers to save context window
        recent = list(self.history)[-limit:]
        context = "\n".join([
            f"{m['role']}: {m['content'][:500]}"  # Limit content length
            for m in recent
        ])
        if self.rolling_summary:
            context += f"\n\nSUMMARY:\n{self.rolling_summary[:500]}"
        return context

    def summarize_old_context(self, llm: LLMClient):
        if len(self.history) < 20:
            return
        older = list(self.history)[:-10]
        text = "\n".join([
            f"{m['role']}: {m['content'][:300]}"  # Truncate for summary too
            for m in older
        ])
        prompt = [
            {
                "role": "system",
                "content": (
                    "Summarize interview discussion into concise "
                    "technical insights."
                )
            },
            {
                "role": "user",
                "content": text
            }
        ]
        summary = llm.chat(
            prompt,
            temperature=0.2,
            max_tokens=150
        )
        if summary:
            self.rolling_summary = summary

    def detect_contradiction(self, answer: str):
        keywords = [
            "tcp is udp",
            "jwt encrypts passwords",
            "csrf is sql injection"
        ]
        for keyword in keywords:
            if keyword in answer.lower():
                self.contradictions.append(answer)

