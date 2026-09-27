# time_manager.py - COMPLETE FIXED VERSION

import time
import threading
from dataclasses import dataclass
from typing import Optional, Callable, Dict
from enum import Enum


class TimerStatus(Enum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    EXPIRED = "EXPIRED"
    STOPPED = "STOPPED"


@dataclass
class TimerConfig:
    """Configuration for time limits"""
    question_time_limit: int = 120  # seconds per question
    session_time_limit: int = 1800  # 30 minutes total session
    warning_threshold: float = 0.8  # 80% of time used triggers warning
    grace_period: int = 10  # seconds of grace after timer expires


class TimeManager:
    """
    Manages time constraints for the interview process.
    Supports both per-question and total session time limits.
    """

    def __init__(self, config: TimerConfig = None):
        self.config = config or TimerConfig()
        self.session_start_time = None
        self.question_start_time = None
        self.current_question_time_remaining = self.config.question_time_limit
        self.session_time_remaining = self.config.session_time_limit

        self.status = TimerStatus.STOPPED
        self._timer_thread = None
        self._stop_event = threading.Event()
        self._callbacks = {
            "question_time_warning": [],
            "question_time_expired": [],
            "session_time_warning": [],
            "session_time_expired": [],
            "time_update": []
        }

        self._lock = threading.Lock()
        self._session_started = False

    def start_session_timer(self):
        """Start the overall session timer"""
        with self._lock:
            if not self._session_started:
                self.session_start_time = time.time()
                self.session_time_remaining = self.config.session_time_limit
                self._session_started = True
                self.status = TimerStatus.RUNNING

                # Start the timer thread if not already running
                if not self._timer_thread or not self._timer_thread.is_alive():
                    self._stop_event.clear()
                    self._timer_thread = threading.Thread(
                        target=self._timer_loop,
                        daemon=True
                    )
                    self._timer_thread.start()

    def start_question_timer(self):
        """Start timer for the current question"""
        with self._lock:
            # Ensure session timer is started
            if not self._session_started:
                self.start_session_timer()

            self.question_start_time = time.time()
            self.current_question_time_remaining = self.config.question_time_limit
            self.status = TimerStatus.RUNNING

            # Reset the timer thread to include question timing
            self._stop_timer_thread()
            self._stop_event.clear()
            self._timer_thread = threading.Thread(
                target=self._timer_loop,
                daemon=True
            )
            self._timer_thread.start()

    def _timer_loop(self):
        """Main timer loop running in separate thread"""
        while not self._stop_event.is_set():
            time.sleep(0.1)  # Check every 100ms

            with self._lock:
                if self.status == TimerStatus.RUNNING:
                    current_time = time.time()

                    # Update question time if question has started
                    if self.question_start_time:
                        elapsed_question = current_time - self.question_start_time
                        self.current_question_time_remaining = max(
                            0,
                            self.config.question_time_limit - elapsed_question
                        )

                    # Update session time if session has started
                    if self.session_start_time:
                        elapsed_session = current_time - self.session_start_time
                        self.session_time_remaining = max(
                            0,
                            self.config.session_time_limit - elapsed_session
                        )

                    # Check for question time warnings
                    if (self.current_question_time_remaining <=
                            self.config.question_time_limit * (1 - self.config.warning_threshold)):
                        self._trigger_callbacks("question_time_warning")

                    # Check for session time warnings
                    if (self.session_time_remaining <=
                            self.config.session_time_limit * (1 - self.config.warning_threshold)):
                        self._trigger_callbacks("session_time_warning")

                    # Check for question time expiration
                    if self.current_question_time_remaining <= 0:
                        self.status = TimerStatus.EXPIRED
                        self._trigger_callbacks("question_time_expired")

                    # Check for session time expiration
                    if self.session_time_remaining <= 0:
                        self.status = TimerStatus.EXPIRED
                        self._trigger_callbacks("session_time_expired")

                    # Trigger time update callback
                    self._trigger_callbacks("time_update")

    def _stop_timer_thread(self):
        """Stop the timer thread"""
        if self._timer_thread and self._timer_thread.is_alive():
            self._stop_event.set()
            self._timer_thread.join(timeout=0.5)

    def pause_question_timer(self):
        """Pause the current question timer"""
        with self._lock:
            if self.status == TimerStatus.RUNNING:
                self.status = TimerStatus.PAUSED
                self._stop_timer_thread()

    def resume_question_timer(self):
        """Resume the current question timer"""
        with self._lock:
            if self.status == TimerStatus.PAUSED:
                self.status = TimerStatus.RUNNING
                self._stop_timer_thread()
                self._stop_event.clear()
                self._timer_thread = threading.Thread(
                    target=self._timer_loop,
                    daemon=True
                )
                self._timer_thread.start()

    def stop_timers(self):
        """Stop all timers"""
        with self._lock:
            self.status = TimerStatus.STOPPED
            self._stop_timer_thread()
            self._session_started = False

    def get_question_time_remaining(self) -> int:
        """Get remaining time for current question in seconds"""
        with self._lock:
            return int(max(0, self.current_question_time_remaining))

    def get_session_time_remaining(self) -> int:
        """Get remaining session time in seconds"""
        with self._lock:
            return int(max(0, self.session_time_remaining))

    def is_question_time_expired(self) -> bool:
        """Check if current question time has expired"""
        with self._lock:
            return (self.status == TimerStatus.EXPIRED or
                    self.current_question_time_remaining <= 0)

    def is_session_time_expired(self) -> bool:
        """Check if session time has expired"""
        with self._lock:
            return self.session_time_remaining <= 0

    def on(self, event_name: str, callback: Callable):
        """Register a callback for a timer event"""
        if event_name in self._callbacks:
            self._callbacks[event_name].append(callback)

    def _trigger_callbacks(self, event_name: str):
        """Trigger all registered callbacks for an event"""
        for callback in self._callbacks.get(event_name, []):
            try:
                callback()
            except Exception as e:
                print(f"Error in timer callback: {e}")

    def reset_question_timer(self):
        """Reset the question timer for the next question"""
        with self._lock:
            self.question_start_time = time.time()
            self.current_question_time_remaining = self.config.question_time_limit
            if self.status == TimerStatus.EXPIRED:
                self.status = TimerStatus.RUNNING

    def get_stats(self) -> Dict:
        """Get timer statistics"""
        with self._lock:
            return {
                "session_started": self._session_started,
                "session_elapsed": self.config.session_time_limit - self.session_time_remaining if self.session_start_time else 0,
                "question_elapsed": self.config.question_time_limit - self.current_question_time_remaining if self.question_start_time else 0,
                "status": self.status.value,
                "session_remaining": self.session_time_remaining,
                "question_remaining": self.current_question_time_remaining
            }