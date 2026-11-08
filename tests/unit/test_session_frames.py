"""ST-N01/F04/F06：Node执行生产页面解帧，不使用网络或浏览器替身断言替代。"""

import subprocess


def test_ST_N01_ST_F04_ST_F06_page_utf8_frames_and_failed_preview():
    subprocess.run(["node", "tests/browser/session_frames.mjs"], check=True, timeout=30)
