import logging
import os
from openai import AsyncOpenAI, APIConnectionError, APIStatusError

from src.ai.provider import get_llm_config

logger = logging.getLogger(__name__)

FALLBACK_MESSAGE = "Hey, my brain is offline right now — can't connect to the AI. Try again in a bit!"


class AIClient:
    def __init__(self):
        provider = os.environ["LLM_PROVIDER"]
        base_url, api_key, model_name = get_llm_config(provider)
        self.model = model_name
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        logger.info("AIClient initialised: provider=%s base_url=%s model=%s", provider, base_url, self.model)

    async def chat(self, messages: list[dict]) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
            reply = response.choices[0].message.content.strip()
            logger.debug("AI reply (%d chars)", len(reply))
            return reply
        except APIConnectionError:
            logger.warning("vLLM connection failed")
            return FALLBACK_MESSAGE
        except APIStatusError as e:
            logger.error("vLLM API error status=%d: %s", e.status_code, e.message)
            return FALLBACK_MESSAGE
        except Exception:
            logger.exception("Unexpected AI error")
            return FALLBACK_MESSAGE
