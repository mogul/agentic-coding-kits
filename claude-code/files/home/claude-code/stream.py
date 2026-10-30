"""Normalize repeated tool IDs from gateways that restamp every argument chunk."""

import json


def encode(event):
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()


async def normalize(response):
    active = None
    next_index = 0
    pending_stop = False
    source_index = None
    buffer = b""
    async for chunk in response:
        buffer += chunk if isinstance(chunk, bytes) else chunk.encode()
        while b"\n\n" in buffer:
            frame, buffer = buffer.split(b"\n\n", 1)
            data = b"\n".join(line[6:] for line in frame.splitlines() if line.startswith(b"data: "))
            event = json.loads(data)
            kind = event["type"]
            if kind == "content_block_start":
                block = event["content_block"]
                source_index = event["index"]
                repeated = (
                    active is not None
                    and block.get("type") == "tool_use"
                    and active["block"].get("type") == "tool_use"
                    and block.get("id") == active["block"].get("id")
                )
                if repeated:
                    if block.get("name") != active["block"].get("name"):
                        raise ValueError("tool ID changed name")
                    pending_stop = False
                    continue
                if active is not None:
                    if not pending_stop:
                        raise ValueError("overlapping content blocks")
                    yield encode({"type": "content_block_stop", "index": active["index"]})
                active = {"index": next_index, "block": block}
                next_index += 1
                pending_stop = False
                event["index"] = active["index"]
            elif kind == "content_block_delta":
                if active is None or pending_stop or event["index"] != source_index:
                    raise ValueError("delta outside active content block")
                event["index"] = active["index"]
            elif kind == "content_block_stop":
                if active is None or event["index"] != source_index:
                    raise ValueError("stop outside active content block")
                pending_stop = True
                continue
            elif kind in ("message_delta", "message_stop", "error"):
                if active is not None:
                    if not pending_stop and kind != "error":
                        raise ValueError("unfinished content block")
                    yield encode({"type": "content_block_stop", "index": active["index"]})
                    active = None
                pending_stop = False
            yield encode(event)
    if buffer.strip() or active is not None:
        raise ValueError("incomplete SSE stream")
