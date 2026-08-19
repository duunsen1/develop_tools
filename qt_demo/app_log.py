"""
应用日志与主线程卡死监控

日志文件：devtools.log（打包后位于 exe 同目录，源码运行位于当前目录）
- 记录应用生命周期、关键操作与异常堆栈
- MainThreadWatchdog：后台线程检测主线程超过阈值未响应时，
  把主线程当时的调用栈写入日志，精确定位"卡死"发生在哪一行
"""

import logging
import os
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

APP_LOGGER = "devtools"


def log_path() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "devtools.log")
    return os.path.join(os.getcwd(), "devtools.log")


def setup_logging() -> str:
    path = log_path()
    handler = RotatingFileHandler(
        path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(threadName)s] %(message)s"
    ))
    logger = logging.getLogger(APP_LOGGER)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.info("应用启动，日志文件: %s", path)
    return path


def install_excepthook() -> None:
    """未捕获异常写入日志，避免窗口模式下悄无声息"""
    logger = logging.getLogger(APP_LOGGER)

    def _hook(etype, value, tb):
        logger.critical("未捕获异常", exc_info=(etype, value, tb))
        sys.__excepthook__(etype, value, tb)

    sys.excepthook = _hook


class MainThreadWatchdog(threading.Thread):
    """主线程卡死监控（守护线程，随进程退出）

    heartbeat_ref 是主线程心跳的引用（如 [last_time] 列表），主线程定期更新；
    若超过 timeout_s 未更新，判定主线程卡死，dump 其调用栈到日志。
    """

    def __init__(self, heartbeat_ref: list, timeout_s: float = 10.0,
                 check_interval_s: float = 2.0):
        super().__init__(daemon=True, name="MainWatchdog")
        self._heartbeat = heartbeat_ref
        self._timeout = timeout_s
        self._interval = check_interval_s

    def run(self):
        logger = logging.getLogger(APP_LOGGER)
        was_stuck = False
        while True:
            time.sleep(self._interval)
            idle = time.time() - self._heartbeat[0]
            if idle >= self._timeout:
                if not was_stuck:
                    logger.critical(
                        "主线程疑似卡死 %.1fs（阈值 %ss），调用栈：\n%s",
                        idle, self._timeout, self._dump_main_stack(),
                    )
                    was_stuck = True
            else:
                was_stuck = False

    @staticmethod
    def _dump_main_stack() -> str:
        frames = sys._current_frames()
        frame = frames.get(threading.main_thread().ident)
        if frame is None:
            return "  （无法获取主线程栈）"
        lines = []
        while frame is not None:
            lines.append(
                f"  {frame.f_code.co_filename}:{frame.f_lineno} in {frame.f_code.co_name}"
            )
            frame = frame.f_back
        return "\n".join(lines)


def start_watchdog(heartbeat: list, timeout_s: float = 10.0,
                   check_interval_s: float = 2.0) -> MainThreadWatchdog:
    watchdog = MainThreadWatchdog(heartbeat, timeout_s, check_interval_s)
    watchdog.start()
    return watchdog
