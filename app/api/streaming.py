"""SSE 响应装配；不登记未完成的持久业务路由。"""

from flask import Response


def stream_response(stream):
    response = Response(stream, mimetype="text/event-stream")
    response.headers.update(
        {
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        }
    )
    response.call_on_close(stream.close)
    return response
