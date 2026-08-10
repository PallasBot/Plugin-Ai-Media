from __future__ import annotations

from pallas.api.runtime import DirectBotAction, DirectWorkResult

from .service import submit_tts_request


async def handle_tts_submit(payload: dict) -> DirectWorkResult | None:
    error = await submit_tts_request(payload)
    if error is None:
        return None
    return DirectWorkResult(
        actions=(
            DirectBotAction(
                action="send_group_msg",
                target_bot_id=int(payload["bot_id"]),
                payload={"group_id": int(payload["group_id"]), "message_text": error},
            ),
        )
    )


def work_handlers():
    return {"tts.submit": handle_tts_submit}
