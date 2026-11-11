"""工具出站连接只发送到经全量检查并固定的地址。"""

import ipaddress
import socket
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from http.client import HTTPConnection, HTTPException
from urllib.parse import urlencode

MAX_RESPONSE = 16 * 1024


class ToolDependencyError(Exception):
    """错误类别可公开，异常信息中不包含目标、凭据或正文。"""


def time_left(deadline):
    timeout = deadline - time.monotonic()
    if timeout <= 0:
        raise ToolDependencyError("timeout")
    return timeout


class ToolTransport:
    def __init__(self, resolve=socket.getaddrinfo):
        self.resolve = resolve
        self.workers = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tool-dns")
        self.dns_slots = threading.BoundedSemaphore(4)
        self.tls = ssl.create_default_context()

    def addresses(self, target, deadline):
        if not self.dns_slots.acquire(blocking=False):
            raise ToolDependencyError("dns")
        try:
            future = self.workers.submit(
                self.resolve, target.host, target.port, 0, socket.SOCK_STREAM
            )
        except RuntimeError:
            self.dns_slots.release()
            raise ToolDependencyError("dns") from None
        future.add_done_callback(lambda _future: self.dns_slots.release())
        try:
            rows = future.result(timeout=time_left(deadline))
        except TimeoutError:
            raise ToolDependencyError("timeout") from None
        except OSError:
            raise ToolDependencyError("dns") from None
        addresses = []
        for family, _, _, _, sockaddr in rows:
            if (
                family not in (socket.AF_INET, socket.AF_INET6)
                or sockaddr[1] != target.port
            ):
                raise ToolDependencyError("address")
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.version == 6 and (ip.ipv4_mapped or ip.scope_id):
                raise ToolDependencyError("address")
            if target.network:
                allowed = ip in target.network
            else:
                allowed = ip.is_global and not ip.is_multicast
            if not allowed:
                raise ToolDependencyError("address")
            addresses.append((family, sockaddr))
        if not addresses:
            raise ToolDependencyError("dns")
        return addresses

    def request(
        self,
        target,
        method,
        path,
        deadline,
        *,
        headers,
        body=None,
        query=None,
        context=None,
        stop=None,
    ):
        family, sockaddr = self.addresses(target, deadline)[0]
        connection = HTTPConnection(target.host, target.port)
        stream = socket.socket(family, socket.SOCK_STREAM)
        timer = None

        def interrupt():
            try:
                stream.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        try:
            if context:
                context.on_cancel(interrupt)
                context.check()
            stream.settimeout(time_left(deadline))
            stream.connect(sockaddr)
            if stream.getpeername()[:2] != sockaddr[:2]:
                raise ToolDependencyError("address")
            if target.scheme == "https":
                stream.settimeout(time_left(deadline))
                stream = self.tls.wrap_socket(stream, server_hostname=target.host)
            timer = threading.Timer(time_left(deadline), interrupt)
            timer.daemon = True
            timer.start()
            if context:
                context.check()
            connection.sock = stream
            if query:
                path += "?" + urlencode(query)
            connection.request(method, path, body=body, headers=headers)
            with connection.getresponse() as response:
                if not 200 <= response.status < 300:
                    raise ToolDependencyError("upstream")
                if (
                    response.getheader("Content-Encoding", "identity").lower()
                    != "identity"
                ):
                    raise ToolDependencyError("response")
                size = response.getheader("Content-Length")
                if size is not None and (
                    not size.isdecimal() or int(size) > MAX_RESPONSE
                ):
                    raise ToolDependencyError("response")
                return (
                    response.status,
                    dict(response.headers.items()),
                    self._read(response, deadline, stop),
                )
        except (OSError, HTTPException, ValueError):
            time_left(deadline)
            raise ToolDependencyError("transport") from None
        finally:
            if timer is not None:
                timer.cancel()
            connection.close()
            stream.close()

    @staticmethod
    def _read(response, deadline, stop):
        data = bytearray()
        while True:
            block = response.read1(MAX_RESPONSE + 1 - len(data))
            time_left(deadline)
            if not block:
                return bytes(data)
            data.extend(block)
            if len(data) > MAX_RESPONSE:
                raise ToolDependencyError("response")
            if stop is not None and stop(response.headers, data):
                return bytes(data)
