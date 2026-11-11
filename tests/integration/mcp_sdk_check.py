"""用固定版本的官方客户端从 MCP 协议边界复验教学服务。"""

import asyncio
import json
import os
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def verify(endpoint):
    headers = {"Authorization": f"Bearer {os.environ['MCP_SERVICE_TOKEN']}"}
    async with (
        streamablehttp_client(endpoint, headers=headers) as (receive, send, session_id),
        ClientSession(receive, send) as session,
    ):
        initialized = await session.initialize()
        assert initialized.protocolVersion == "2025-06-18"
        assert initialized.capabilities.tools is not None
        assert session_id()
        listed = await session.list_tools()
        tools = {item.name: item for item in listed.tools}
        assert set(tools) == {"formula_hint", "unit_convert"}
        assert all(
            item.inputSchema["additionalProperties"] is False for item in tools.values()
        )

        hint = await session.call_tool(
            "formula_hint", {"topic": "linear_equation", "stage": "start"}
        )
        assert not hint.isError
        assert json.loads(hint.content[0].text) == {
            "hint_id": "linear_equation:start",
            "hint": "先找出含未知数的项，考虑如何在等式两边做同一种运算。",
        }
        result = await session.call_tool(
            "unit_convert", {"value": -1.234567, "from_unit": "m", "to_unit": "mm"}
        )
        assert not result.isError
        assert json.loads(result.content[0].text) == {
            "value": "-1234.567",
            "unit": "mm",
            "factor": "1000",
        }
        cross_dimension = await session.call_tool(
            "unit_convert", {"value": 1, "from_unit": "m", "to_unit": "kg"}
        )
        assert cross_dimension.isError
    print("MCP 2025-06-18 独立客户端握手、发现、两项调用及跨量纲拒绝通过")


if __name__ == "__main__":
    asyncio.run(verify(sys.argv[1]))
