"""有界段级流基础；业务授权、结构校验与持久提交由调用方注入。"""

import json
import queue
import threading
import time

from app.services.access import AccessDenied

LONG_REQUEST_LIMIT = 4
HEARTBEAT_SECONDS = 0.25
STREAM_SECONDS = 35


def dependency_error():
    return AccessDenied(503, 1500, "依赖服务暂不可用，请稍后重试")


def invalid_output():
    return AccessDenied(502, 1501, "生成结果未通过校验，请重试")


class StreamCancelled(Exception):
    pass


class LongRequestCapacity:
    """仅当前单 worker 适用；流和后续同步应用共用同一个实例。"""

    def __init__(self, limit=LONG_REQUEST_LIMIT, *, draining=lambda: False):
        if type(limit) is not int or not 1 <= limit <= LONG_REQUEST_LIMIT:
            raise ValueError("长请求上限必须为1–4")
        self.limit = limit
        self.draining = draining
        self._active = 0
        self._lock = threading.Lock()

    @property
    def active(self):
        with self._lock:
            return self._active

    def reserve(self):
        with self._lock:
            if self.draining():
                raise dependency_error()
            if self._active >= self.limit:
                raise AccessDenied(429, 1600, "长请求已满，请稍后重试", retry_after=1)
            self._active += 1
        return Reservation(self)

    def _release(self):
        with self._lock:
            self._active -= 1


class Reservation:
    def __init__(self, capacity):
        self.capacity = capacity
        self._released = False
        self._lock = threading.Lock()

    def release(self):
        with self._lock:
            if not self._released:
                self._released = True
                self.capacity._release()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.release()


class StreamContext:
    def __init__(self, deadline, *, draining=lambda: False, clock=time.monotonic):
        self.deadline = deadline
        self.draining = draining
        self.clock = clock
        self.cancelled = threading.Event()
        self._callbacks = []
        self._lock = threading.Lock()

    def check(self):
        if self.cancelled.is_set():
            raise StreamCancelled
        if self.draining() or self.clock() >= self.deadline:
            raise dependency_error()

    def on_cancel(self, callback):
        with self._lock:
            already_cancelled = self.cancelled.is_set()
            if not already_cancelled:
                self._callbacks.append(callback)
        if already_cancelled:
            self._cancel_callback(callback)

    @staticmethod
    def _cancel_callback(callback):
        try:
            callback()
        except Exception:
            # 取消尽力执行，不能用上游错误正文覆盖安全终态。
            pass

    def cancel(self):
        with self._lock:
            if self.cancelled.is_set():
                return
            self.cancelled.set()
            callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            self._cancel_callback(callback)


class ValidatedStream:
    """惰性启动有界生产者；结束/断开后才释放槽位，生产者未退出时不提前释放。

    prepare/retrieve 必须在 reserve 后、响应前完成；produce 接收取消上下文，
    每次最多阻塞到单调用超时。validate 校验原始结构并返回可公开的完整段落，
    recheck 重验当前身份/配置/来源；commit 须原子校验并提交成功记录后才返回。
    """

    def __init__(
        self,
        reservation,
        *,
        produce,
        validate,
        recheck,
        commit,
        metadata,
        request_id,
        validate_final,
        on_abort=lambda: None,
        clock=time.monotonic,
        deadline=None,
    ):
        self.reservation = reservation
        self.produce = produce
        self.validate = validate
        self.recheck = recheck
        self.commit = commit
        self.metadata = metadata
        self.request_id = request_id
        self.validate_final = validate_final
        self.on_abort = on_abort
        self.context = StreamContext(
            min(clock() + STREAM_SECONDS, deadline)
            if deadline is not None
            else clock() + STREAM_SECONDS,
            draining=reservation.capacity.draining,
            clock=clock,
        )
        self.queue = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._started = False
        self._worker_done = False
        self._closed = False
        self._committed = False
        self._iterator = self._events()

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._iterator)

    def _frame(self, event, payload):
        return (
            "event: "
            + event
            + "\ndata: "
            + json.dumps(
                {"code": 0, "data": payload, "request_id": self.request_id},
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n\n"
        ).encode("utf-8")

    def _put(self, value):
        while not self.context.cancelled.is_set():
            try:
                self.queue.put(value, timeout=HEARTBEAT_SECONDS)
                return
            except queue.Full:
                self.context.check()
        raise StreamCancelled

    def _work(self):
        source = None
        try:
            source = iter(self.produce(self.context))
            for payload in source:
                self.context.check()
                self._put(("paragraph", payload))
            self._put(("complete", None))
        except StreamCancelled:
            pass
        except AccessDenied as error:
            self._put_error(error)
        except Exception:
            self._put_error(dependency_error())
        finally:
            if source is not None and hasattr(source, "close"):
                try:
                    source.close()
                except Exception:
                    pass
            with self._lock:
                self._worker_done = True
                if self._closed:
                    self.reservation.release()

    def _put_error(self, error):
        try:
            self._put(("error", error))
        except (StreamCancelled, AccessDenied):
            pass

    def _events(self):
        paragraphs, raw, length = [], [], 0
        try:
            self.context.check()
            self.recheck()
            with self._lock:
                if self._closed:
                    raise StreamCancelled
                self._started = True
                try:
                    threading.Thread(target=self._work, daemon=True).start()
                except Exception:
                    self._worker_done = True
                    raise
            self.recheck()
            yield self._frame("meta", self.metadata)
            while True:
                self.context.check()
                try:
                    event, value = self.queue.get(timeout=HEARTBEAT_SECONDS)
                except queue.Empty:
                    self.recheck()
                    # 心跳不含业务文本，使断开的下游能及时触发WSGI close。
                    yield b": keepalive\n\n"
                    continue
                if event == "error":
                    raise value
                self.recheck()
                self.context.check()
                if event == "complete":
                    if not paragraphs:
                        raise invalid_output()
                    text = "".join(paragraphs)
                    self.validate_final(raw, text)
                    self.context.check()
                    result = self.commit(text)
                    self._committed = True
                    yield self._frame("done", result)
                    return
                text = self.validate(value)
                if not isinstance(text, str) or not text or "\0" in text:
                    raise invalid_output()
                try:
                    text.encode("utf-8")
                except UnicodeError:
                    raise invalid_output() from None
                length += len(text)
                if length > 12000 or len(paragraphs) >= 8:
                    raise invalid_output()
                self.context.check()
                self.recheck()
                paragraphs.append(text)
                raw.append(value)
                yield self._frame("delta", {"text": text})
        except StreamCancelled:
            return
        except AccessDenied as error:
            yield (
                "event: error\ndata: "
                + json.dumps(
                    {
                        "code": error.code,
                        "message": error.message,
                        "data": None,
                        "request_id": self.request_id,
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            ).encode("utf-8")
        except Exception:
            error = dependency_error()
            yield (
                "event: error\ndata: "
                + json.dumps(
                    {
                        "code": error.code,
                        "message": error.message,
                        "data": None,
                        "request_id": self.request_id,
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            ).encode("utf-8")
        finally:
            self._finish()

    def _finish(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            release = not self._started or self._worker_done
        self.context.cancel()
        try:
            if not self._committed:
                self.on_abort()
        finally:
            if release:
                self.reservation.release()

    def close(self):
        try:
            self._iterator.close()
        finally:
            self._finish()
