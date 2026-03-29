import logging

import httpx

from app.config import settings
from app.exceptions import LLMConfigurationException
from app.exceptions import LLMServiceException

logger = logging.getLogger(__name__)


class OpenRouterService:
    def __init__(self) -> None:
        self._api_key = settings.OPENROUTER_API_KEY
        self._base_url = settings.OPENROUTER_BASE_URL.rstrip("/")
        self._model = settings.OPENROUTER_MODEL
        self._timeout = settings.OPENROUTER_TIMEOUT_SECONDS

    def _ensure_configured(self) -> None:
        if not self._api_key:
            raise LLMConfigurationException(
                "LLM не настроена: задайте OPENROUTER_API_KEY для работы с OpenRouter."
            )

    async def _complete(self, system_prompt: str, user_prompt: str) -> str:
        self._ensure_configured()

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "OpenRouter API returned %s: %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise LLMServiceException(
                "OpenRouter вернул ошибку при обработке запроса."
            ) from exc
        except httpx.HTTPError as exc:
            logger.error("OpenRouter request failed: %s", exc)
            raise LLMServiceException("Не удалось обратиться к OpenRouter API.") from exc

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise LLMServiceException("OpenRouter не вернул вариантов ответа.")

        message = choices[0].get("message") or {}
        content = message.get("content")
        if not content or not isinstance(content, str):
            raise LLMServiceException("OpenRouter вернул пустой ответ.")

        return content.strip()

    async def generate_title(self, details: str, current_title: str | None = None) -> str:
        system_prompt = (
            "Ты помогаешь придумывать короткие и информативные заголовки заметок на русском языке. "
            "Верни только один заголовок без кавычек, без пояснений и не длиннее 80 символов."
        )
        user_prompt = (
            f"Текущий заголовок: {current_title or 'нет'}\n"
            f"Описание заметки:\n{details.strip()}\n\n"
            "Сгенерируй лучший заголовок."
        )
        return await self._complete(system_prompt, user_prompt)

    async def generate_summary(self, title: str | None, details: str | None) -> str:
        system_prompt = (
            "Ты делаешь краткие рефераты заметок на русском языке. "
            "Верни только короткое изложение сути заметки в 1-2 предложениях, без заголовка и без маркированных списков."
        )
        user_prompt = (
            f"Заголовок: {title or 'нет'}\n"
            f"Текст заметки:\n{(details or '').strip()}"
        )
        return await self._complete(system_prompt, user_prompt)

    async def suggest_tag(
        self,
        title: str | None,
        details: str | None,
        cluster_context: str,
        existing_tags: list[str],
    ) -> str:
        system_prompt = (
            "Ты подбираешь краткий тег для заметки на русском языке. "
            "Верни только один тег из 1-3 слов, без кавычек и без пояснений."
        )
        user_prompt = (
            f"Заголовок заметки: {title or 'нет'}\n"
            f"Описание заметки:\n{(details or '').strip()}\n\n"
            f"Существующие теги в системе: {', '.join(existing_tags) if existing_tags else 'нет'}\n"
            f"Похожие заметки из того же кластера:\n{cluster_context}\n\n"
            "Предложи лучший тег."
        )
        return await self._complete(system_prompt, user_prompt)
