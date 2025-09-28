"""OData клиент для подключения к 1С."""

import base64
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, quote

import httpx
import xmltodict
from loguru import logger
from pydantic import BaseModel, Field

from .cache import DataCache


class ODataConfig(BaseModel):
    """Конфигурация подключения к OData 1C."""
    
    base_url: str = Field(..., description="Базовый URL OData сервиса 1C")
    username: str = Field(..., description="Имя пользователя")
    password: str = Field(..., description="Пароль")
    timeout: int = Field(default=30, description="Таймаут запросов в секундах")
    verify_ssl: bool = Field(default=True, description="Проверка SSL сертификата")


class ODataClient:
    """Клиент для работы с OData 1C."""
    
    def __init__(self, config: ODataConfig):
        self.config = config
        self._client = None
        
        # Инициализируем кэш данных
        cache_dir = os.getenv("METADATA_CACHE_DIR", "cache")
        cache_ttl = int(os.getenv("METADATA_CACHE_TTL_HOURS", "24"))
        self._cache = DataCache(cache_dir=cache_dir, cache_ttl_hours=cache_ttl)
        
        logger.info(f"Инициализация OData клиента для {config.base_url}")
    
    def _get_client(self) -> httpx.AsyncClient:
        """Получить HTTP клиент с настроенной аутентификацией."""
        if self._client is None:
            # Создаем Basic Auth заголовок
            credentials = f"{self.config.username}:{self.config.password}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
            
            headers = {
                "Authorization": f"Basic {encoded_credentials}",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=self.config.timeout,
                verify=self.config.verify_ssl
            )
            
        return self._client
    
    async def close(self):
        """Закрыть HTTP клиент."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def get_metadata(self, use_cache: bool = True) -> Dict[str, Any]:
        """Получить метаданные OData сервиса."""
        
        # Пытаемся получить из кэша
        if use_cache:
            cached_metadata = self._cache.get_raw_metadata()
            if cached_metadata:
                logger.info("Метаданные загружены из кэша")
                return cached_metadata.get("metadata", {})
        
        # Запрашиваем метаданные с сервера
        client = self._get_client()
        url = urljoin(self.config.base_url, "$metadata")
        
        logger.info(f"Запрос метаданных с сервера: {url}")
        
        try:
            response = await client.get(url)
            response.raise_for_status()
            
            # Парсим XML метаданные
            metadata_xml = response.text
            metadata_dict = xmltodict.parse(metadata_xml)
            
            # Сохраняем в кэш
            if use_cache:
                self._cache.save_raw_metadata(metadata_dict)
            
            logger.debug("Метаданные успешно получены с сервера")
            return metadata_dict
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка HTTP при получении метаданных: {e}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при получении метаданных: {e}")
            raise
    
    async def query_data(
        self, 
        entity_set: str, 
        filter_expr: Optional[str] = None,
        select_fields: Optional[List[str]] = None,
        top: Optional[int] = None,
        skip: Optional[int] = None,
        order_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """Выполнить запрос к данным."""
        client = self._get_client()
        url = urljoin(self.config.base_url, entity_set)
        
        # Строим параметры запроса
        params = {}
        if filter_expr:
            params["$filter"] = filter_expr
        if select_fields:
            params["$select"] = ",".join(select_fields)
        if top:
            params["$top"] = str(top)
        if skip:
            params["$skip"] = str(skip)
        if order_by:
            params["$orderby"] = order_by
        
        logger.info(f"Запрос данных: {url} с параметрами {params}")
        
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            logger.debug(f"Получено записей: {len(data.get('value', []))}")
            return data
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка HTTP при запросе данных: {e}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при запросе данных: {e}")
            raise
    
    async def create_entity(self, entity_set: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Создать новую сущность."""
        client = self._get_client()
        url = urljoin(self.config.base_url, entity_set)
        
        logger.info(f"Создание сущности в {entity_set}")
        
        try:
            response = await client.post(url, json=data)
            response.raise_for_status()
            
            result = response.json()
            logger.debug("Сущность успешно создана")
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка HTTP при создании сущности: {e}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при создании сущности: {e}")
            raise
    
    async def update_entity(
        self, 
        entity_set: str, 
        entity_key: str, 
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Обновить существующую сущность."""
        client = self._get_client()
        url = urljoin(self.config.base_url, f"{entity_set}(guid'{entity_key}')")
        
        logger.info(f"Обновление сущности {entity_key} в {entity_set}")
        
        try:
            response = await client.patch(url, json=data)
            response.raise_for_status()
            
            if response.status_code == 204:
                # Успешное обновление без содержимого
                return {"success": True}
            else:
                result = response.json()
                logger.debug("Сущность успешно обновлена")
                return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка HTTP при обновлении сущности: {e}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при обновлении сущности: {e}")
            raise
    
    async def delete_entity(self, entity_set: str, entity_key: str) -> bool:
        """Удалить сущность."""
        client = self._get_client()
        url = urljoin(self.config.base_url, f"{entity_set}(guid'{entity_key}')")
        
        logger.info(f"Удаление сущности {entity_key} из {entity_set}")
        
        try:
            response = await client.delete(url)
            response.raise_for_status()
            
            logger.debug("Сущность успешно удалена")
            return True
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка HTTP при удалении сущности: {e}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при удалении сущности: {e}")
            raise
    
    async def get_entity_by_key(self, entity_set: str, entity_key: str) -> Dict[str, Any]:
        """Получить сущность по ключу."""
        client = self._get_client()
        url = urljoin(self.config.base_url, f"{entity_set}(guid'{entity_key}')")
        
        logger.info(f"Получение сущности {entity_key} из {entity_set}")
        
        try:
            response = await client.get(url)
            response.raise_for_status()
            
            result = response.json()
            logger.debug("Сущность успешно получена")
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка HTTP при получении сущности: {e}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при получении сущности: {e}")
            raise
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Получить информацию о состоянии кэша метаданных."""
        return self._cache.get_cache_info()
    
    def clear_metadata_cache(self) -> None:
        """Очистить кэш метаданных."""
        self._cache.clear_cache()
        logger.info("Кэш метаданных очищен")
