#!/bin/sh
set -eu

ready=/tmp/campusclaw-ready
probe_pid=
server_pid=

cleanup() {
    if [ -n "$probe_pid" ]; then
        kill "$probe_pid" 2>/dev/null || :
        wait "$probe_pid" 2>/dev/null || :
    fi
    rm -f "$ready"
    if [ -n "$server_pid" ]; then
        kill -QUIT "$server_pid" 2>/dev/null || :
        wait "$server_pid" 2>/dev/null || :
    fi
}

trap cleanup EXIT
trap 'exit 0' TERM INT QUIT
rm -f "$ready"

# 在独立进程探测就绪，让业务请求只检查本地标记。
(
    while :; do
        if wget -q -T 2 -O /dev/null "${1:-http://app:8080/health}"; then
            touch "$ready"
        else
            rm -f "$ready"
        fi
        sleep 1
    done
) &
probe_pid=$!

nginx -g 'daemon off;' &
server_pid=$!

# 探测进程异常退出时也停止接流，避免沿用最后一次就绪结果。
while kill -0 "$probe_pid" 2>/dev/null && kill -0 "$server_pid" 2>/dev/null; do
    sleep 1
done
exit 1
