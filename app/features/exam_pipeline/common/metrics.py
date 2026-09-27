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
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==============================================================================
# METRICS
# ==============================================================================
class Metrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.llm_calls = 0
        self.llm_failures = 0
        self.total_llm_latency = 0.0
        self.total_retrieval_latency = 0.0
        self.questions_generated = 0

    def llm_success(self, latency: float):
        with self.lock:
            self.llm_calls += 1
            self.total_llm_latency += latency

    def llm_failure(self):
        with self.lock:
            self.llm_failures += 1

    def retrieval(self, latency: float):
        with self.lock:
            self.total_retrieval_latency += latency

    def summary(self) -> Dict[str, Any]:
        with self.lock:
            avg_llm = (
                self.total_llm_latency / self.llm_calls
                if self.llm_calls else 0
            )
            return {
                "llm_calls": self.llm_calls,
                "llm_failures": self.llm_failures,
                "avg_llm_latency": round(avg_llm, 2),
                "retrieval_latency": round(self.total_retrieval_latency, 2),
                "questions_generated": self.questions_generated
            }

