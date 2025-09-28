"""Основной MCP сервер для работы с 1С."""

import os
import sys
from typing import Optional

from fastmcp import FastMCP
from loguru import logger

from .client import ODataConfig
from .tools import create_1c_tools
from dotenv import load_dotenv
import dotenv
dotenv.load_dotenv()

def setup_logging():
    """Настройка логирования."""
    logger.remove()  # Удаляем стандартный обработчик
    
    # Добавляем обработчик для консоли
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    # Добавляем обработчик для файла (если нужен)
    log_file = os.getenv("MCP_1C_LOG_FILE")
    if log_file:
        logger.add(
            log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG",
            rotation="10 MB",
            retention="7 days"
        )


def create_server() -> FastMCP:
    """Создать и настроить MCP сервер."""
    setup_logging()
    
    logger.info("Инициализация MCP сервера для 1С")
    
    # Получаем конфигурацию из переменных окружения
    config = ODataConfig(
        base_url=os.getenv("ODATA_BASE_URL", "http://localhost/Base/odata/standard.odata/"),
        username=os.getenv("ODATA_USERNAME", ""),
        password=os.getenv("ODATA_PASSWORD", ""),
        timeout=int(os.getenv("ODATA_TIMEOUT", "30")),
        verify_ssl=os.getenv("ODATA_VERIFY_SSL", "true").lower() == "true"
    )
    
    if not config.username or not config.password:
        logger.warning("Не указаны учетные данные для подключения к 1С")
        logger.info("Используйте переменные окружения ODATA_USERNAME и ODATA_PASSWORD")
    
    # Создаем MCP сервер с инструментами
    mcp = create_1c_tools(config)
    
    # Добавляем ресурсы
    @mcp.resource("config://odata")
    def get_odata_config() -> dict:
        """Получить конфигурацию OData подключения."""
        return {
            "base_url": config.base_url,
            "username": config.username,
            "timeout": config.timeout,
            "verify_ssl": config.verify_ssl,
            "description": "Конфигурация подключения к OData сервису 1С"
        }
    
    @mcp.resource("help://tools")
    def get_tools_help() -> dict:
        """Получить справку по доступным инструментам."""
        return {
            "tools": {
                "fetch_1c_metadata": "Получить и сохранить структуру метаобъектов 1С в JSON файл",
                "fetch_1c_data": "Получить данные из 1С и сохранить в JSON файл",
                "get_1c_entity": "Получить конкретную сущность по ключу",
                "create_1c_entity": "Создать новую сущность (справочник, документ и др.)",
                "update_1c_entity": "Обновить существующую сущность в 1С",
                "create_1c_document": "Создать новый документ в 1С (устаревшая функция)",
                "update_1c_document": "Обновить существующий документ (устаревшая функция)",
                "delete_1c_document": "Удалить документ из 1С",
                "create_rtu_document": "Создать документ РТиУ на основании другого документа",
                "list_cached_data": "Получить список всех сохраненных JSON файлов с данными",
                "filter_local_data": "Фильтровать и сортировать данные из локального JSON файла",
                "count_local_data": "Подсчитать записи в локальном JSON файле",
                "get_file_structure": "Получить структуру JSON файла (поля, типы, примеры)",
                "get_cache_info": "Получить информацию о состоянии кэша",
                "clear_metadata_cache": "Очистить кэш метаданных",
                "clear_data_cache": "Очистить все сохраненные данные"
            },
            "examples": {
                "fetch_data": {
                    "entity_set": "Catalog_Products",
                    "filter_expr": "Description eq 'Товар 1'",
                    "select_fields": "Ref_Key,Description,Code",
                    "top": 10
                },
                "filter_local": {
                    "file_name": "Catalog_Products_abc123.json",
                    "filters": {"Description": "Товар"},
                    "select_fields": ["Ref_Key", "Description"],
                    "sort_by": "Description",
                    "sort_desc": False,
                    "limit": 5
                },
                "get_structure": {
                    "file_name": "Catalog_Products_abc123.json"
                },
                "create_entity": {
                    "entity_set": "Catalog_Products",
                    "data": {
                        "Code": "PROD001",
                        "Description": "Новый товар",
                        "Price": 1000.00
                    }
                },
                "update_entity": {
                    "entity_set": "Catalog_Products",
                    "entity_key": "guid'...'",
                    "data": {
                        "Description": "Обновленное наименование",
                        "Price": 1200.00
                    }
                },
                "create_document": {
                    "document_type": "Document_SalesOrder",
                    "data": {
                        "Number": "SO-001",
                        "Organization_Key": "guid'...'",
                        "Counterparty_Key": "guid'...'"
                    }
                }
            },
            "workflow": {
                "description": "Рекомендуемый порядок работы",
                "steps": [
                    "1. fetch_1c_metadata() - получить структуру метаобъектов",
                    "2. fetch_1c_data() - получить данные и сохранить в JSON",
                    "3. list_cached_data() - посмотреть список сохраненных файлов",
                    "4. get_file_structure() - изучить структуру файла",
                    "5. filter_local_data() с сортировкой - работать с локальными данными"
                ]
            }
        }
    
    logger.info("MCP сервер успешно создан")
    return mcp


def main():
    """Точка входа для запуска сервера."""
    try:
        mcp = create_server()
        logger.info("Запуск MCP сервера...")
        mcp.run('sse')
    except KeyboardInterrupt:
        logger.info("Сервер остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка при запуске сервера: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
