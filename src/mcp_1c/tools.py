"""MCP инструменты для работы с 1С."""

from typing import Any, Dict, List, Optional
from datetime import datetime

from fastmcp import FastMCP
from loguru import logger
from pydantic import BaseModel, Field

from .client import ODataClient, ODataConfig


class MetadataInfo(BaseModel):
    """Информация о метаданных 1С."""
    entity_sets: List[str] = Field(default_factory=list, description="Список наборов сущностей")
    entity_types: Dict[str, List[str]] = Field(default_factory=dict, description="Типы сущностей и их поля")
    functions: List[str] = Field(default_factory=list, description="Доступные функции")


class QueryResult(BaseModel):
    """Результат запроса к данным 1С."""
    data: List[Dict[str, Any]] = Field(default_factory=list, description="Данные")
    count: int = Field(default=0, description="Количество записей")
    has_more: bool = Field(default=False, description="Есть ли еще данные")


class DocumentCreateRequest(BaseModel):
    """Запрос на создание документа."""
    document_type: str = Field(..., description="Тип документа")
    data: Dict[str, Any] = Field(..., description="Данные документа")


class RTUDocumentRequest(BaseModel):
    """Запрос на создание документа РТиУ."""
    base_document_ref: str = Field(..., description="Ссылка на базовый документ")
    organization_ref: str = Field(..., description="Ссылка на организацию")
    contractor_ref: str = Field(..., description="Ссылка на контрагента")
    warehouse_ref: str = Field(..., description="Ссылка на склад")
    items: List[Dict[str, Any]] = Field(..., description="Номенклатура для реализации")
    comment: Optional[str] = Field(None, description="Комментарий")


def _parse_metadata_to_info(metadata: Dict[str, Any]) -> MetadataInfo:
    """Парсить сырые метаданные в структурированную информацию."""
    info = MetadataInfo()
    
    # Извлекаем информацию из XML метаданных
    schema = metadata.get("edmx:Edmx", {}).get("edmx:DataServices", {}).get("Schema", {})
    
    if isinstance(schema, dict):
        # Наборы сущностей
        entity_container = schema.get("EntityContainer", {})
        if isinstance(entity_container, dict):
            entity_sets = entity_container.get("EntitySet", [])
            if isinstance(entity_sets, list):
                info.entity_sets = [es.get("@Name", "") for es in entity_sets if "@Name" in es]
            elif isinstance(entity_sets, dict) and "@Name" in entity_sets:
                info.entity_sets = [entity_sets["@Name"]]
        
        # Типы сущностей
        entity_types = schema.get("EntityType", [])
        if isinstance(entity_types, list):
            for et in entity_types:
                if "@Name" in et:
                    properties = et.get("Property", [])
                    if isinstance(properties, list):
                        info.entity_types[et["@Name"]] = [
                            p.get("@Name", "") for p in properties if "@Name" in p
                        ]
                    elif isinstance(properties, dict) and "@Name" in properties:
                        info.entity_types[et["@Name"]] = [properties["@Name"]]
        elif isinstance(entity_types, dict) and "@Name" in entity_types:
            properties = entity_types.get("Property", [])
            if isinstance(properties, list):
                info.entity_types[entity_types["@Name"]] = [
                    p.get("@Name", "") for p in properties if "@Name" in p
                ]
            elif isinstance(properties, dict) and "@Name" in properties:
                info.entity_types[entity_types["@Name"]] = [properties["@Name"]]
        
        # Функции
        functions = schema.get("Function", [])
        if isinstance(functions, list):
            info.functions = [f.get("@Name", "") for f in functions if "@Name" in f]
        elif isinstance(functions, dict) and "@Name" in functions:
            info.functions = [functions["@Name"]]
    
    return info


def create_1c_tools(config: ODataConfig) -> FastMCP:
    """Создать MCP сервер с инструментами для работы с 1С."""
    
    mcp = FastMCP(name="1C OData MCP Server")
    client = ODataClient(config)
    

    @mcp.tool
    async def fetch_1c_metadata(use_cache: bool = True) -> Dict[str, Any]:
        """Получить и сохранить структуру метаобъектов 1С в JSON файл."""
        try:
            logger.info("Получение и сохранение метаданных 1С")
            
            # Пытаемся получить обработанные метаданные из кэша
            if use_cache:
                cached_info = client._cache.get_parsed_metadata()
                if cached_info:
                    logger.info("Метаданные уже есть в кэше")
                    return {
                        "status": "success", 
                        "message": "Метаданные загружены из кэша",
                        "cache_file": "cache/metadata_info.json",
                        "entity_sets_count": len(cached_info.get("metadata_info", {}).get("entity_sets", [])),
                        "from_cache": True
                    }
            
            # Получаем сырые метаданные (из кэша или с сервера)
            metadata = await client.get_metadata(use_cache=use_cache)
            
            # Парсим метаданные для извлечения полезной информации
            info = _parse_metadata_to_info(metadata)
            
            # Сохраняем обработанные метаданные в кэш
            if use_cache:
                client._cache.save_parsed_metadata(info.dict())
            
            logger.info(f"Найдено наборов сущностей: {len(info.entity_sets)}")
            return {
                "status": "success",
                "message": f"Метаданные успешно сохранены в JSON файл",
                "cache_file": "cache/metadata_info.json", 
                "entity_sets_count": len(info.entity_sets),
                "entity_types_count": len(info.entity_types),
                "functions_count": len(info.functions),
                "from_cache": False
            }
            
        except Exception as e:
            logger.error(f"Ошибка при получении метаданных: {e}")
            return {
                "status": "error",
                "message": f"Ошибка при получении метаданных: {str(e)}"
            }
    
    @mcp.tool
    async def fetch_1c_data(
        entity_set: str,
        filter_expr: Optional[str] = None,
        select_fields: Optional[str] = None,
        top: Optional[int] = None,
        skip: Optional[int] = None,
        order_by: Optional[str] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """Получить данные из 1С и сохранить в JSON файл."""
        try:
            logger.info(f"Запрос и сохранение данных из {entity_set}")
            
            # Формируем параметры запроса
            params = {}
            if filter_expr:
                params["filter"] = filter_expr
            if select_fields:
                params["select"] = select_fields
            if top:
                params["top"] = top
            if skip:
                params["skip"] = skip
            if order_by:
                params["orderby"] = order_by
            
            # Проверяем кэш
            if use_cache:
                cached_data = client._cache.get_query_data(entity_set, params)
                if cached_data:
                    logger.info("Данные уже есть в кэше")
                    return {
                        "status": "success",
                        "message": "Данные загружены из кэша",
                        "entity_set": entity_set,
                        "record_count": cached_data.get("record_count", 0),
                        "from_cache": True,
                        "query_params": params
                    }
            
            # Преобразуем строку полей в список
            select_list = None
            if select_fields:
                select_list = [field.strip() for field in select_fields.split(",")]
            
            # Запрашиваем данные с сервера
            data = await client.query_data(
                entity_set=entity_set,
                filter_expr=filter_expr,
                select_fields=select_list,
                top=top,
                skip=skip,
                order_by=order_by
            )
            
            records = data.get("value", [])
            
            # Сохраняем данные в кэш
            if use_cache and records:
                file_path = client._cache.save_query_data(entity_set, params, records)
                logger.info(f"Данные сохранены в файл: {file_path}")
            
            logger.info(f"Получено и сохранено записей: {len(records)}")
            return {
                "status": "success",
                "message": f"Данные успешно получены и сохранены в JSON файл",
                "entity_set": entity_set,
                "record_count": len(records),
                "has_more": data.get("@odata.nextLink") is not None,
                "from_cache": False,
                "query_params": params
            }
            
        except Exception as e:
            logger.error(f"Ошибка при запросе данных: {e}")
            return {
                "status": "error",
                "message": f"Ошибка при запросе данных: {str(e)}"
            }
    
    @mcp.tool
    async def get_1c_entity(entity_set: str, entity_key: str) -> Dict[str, Any]:
        """Получить конкретную сущность 1С по ключу."""
        try:
            logger.info(f"Получение сущности {entity_key} из {entity_set}")
            
            result = await client.get_entity_by_key(entity_set, entity_key)
            
            logger.info("Сущность успешно получена")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при получении сущности: {e}")
            raise
    
    @mcp.tool
    async def create_1c_document(request: DocumentCreateRequest) -> Dict[str, Any]:
        """Создать документ в 1С."""
        try:
            logger.info(f"Создание документа типа {request.document_type}")
            
            # Добавляем системные поля если их нет
            data = request.data.copy()
            if "Date" not in data:
                data["Date"] = datetime.now().isoformat()
            if "Posted" not in data:
                data["Posted"] = False
            
            result = await client.create_entity(request.document_type, data)
            
            logger.info("Документ успешно создан")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при создании документа: {e}")
            raise
    
    @mcp.tool
    async def update_1c_document(
        entity_set: str, 
        entity_key: str, 
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Обновить документ в 1С."""
        try:
            logger.info(f"Обновление документа {entity_key} в {entity_set}")
            
            result = await client.update_entity(entity_set, entity_key, data)
            
            logger.info("Документ успешно обновлен")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении документа: {e}")
            raise
    
    @mcp.tool
    async def delete_1c_document(entity_set: str, entity_key: str) -> Dict[str, bool]:
        """Удалить документ из 1С."""
        try:
            logger.info(f"Удаление документа {entity_key} из {entity_set}")
            
            success = await client.delete_entity(entity_set, entity_key)
            
            logger.info("Документ успешно удален")
            return {"success": success}
            
        except Exception as e:
            logger.error(f"Ошибка при удалении документа: {e}")
            raise
    
    @mcp.tool
    async def create_rtu_document(request: RTUDocumentRequest) -> Dict[str, Any]:
        """Создать документ РТиУ (Реализация товаров и услуг) на основании другого документа."""
        try:
            logger.info(f"Создание документа РТиУ на основании {request.base_document_ref}")
            
            # Получаем базовый документ для проверки
            base_doc = await client.get_entity_by_key("Document_SalesOrder", request.base_document_ref)
            
            if not base_doc:
                raise ValueError("Базовый документ не найден")
            
            # Формируем данные документа РТиУ с бизнес-правилами
            rtu_data = {
                "Date": datetime.now().isoformat(),
                "Posted": False,
                "Organization_Key": request.organization_ref,
                "Counterparty_Key": request.contractor_ref,
                "Warehouse_Key": request.warehouse_ref,
                "BasisDocument_Key": request.base_document_ref,
                "Comment": request.comment or f"Создано на основании документа {base_doc.get('Number', '')}",
                "ResponsiblePerson_Key": base_doc.get("ResponsiblePerson_Key"),
                "Currency_Key": base_doc.get("Currency_Key"),
                "PriceIncludesVAT": base_doc.get("PriceIncludesVAT", True),
            }
            
            # Создаем основной документ
            rtu_doc = await client.create_entity("Document_GoodsIssue", rtu_data)
            
            # Добавляем табличную часть с товарами
            if request.items:
                for item in request.items:
                    tabular_data = {
                        "Ref_Key": rtu_doc["Ref_Key"],
                        "LineNumber": item.get("LineNumber", 1),
                        "Product_Key": item["Product_Key"],
                        "Quantity": item["Quantity"],
                        "Price": item.get("Price", 0),
                        "Amount": item.get("Amount", item["Quantity"] * item.get("Price", 0)),
                        "VAT_Key": item.get("VAT_Key"),
                        "VATAmount": item.get("VATAmount", 0),
                    }
                    
                    await client.create_entity("Document_GoodsIssue_Products", tabular_data)
            
            logger.info("Документ РТиУ успешно создан")
            return rtu_doc
            
        except Exception as e:
            logger.error(f"Ошибка при создании документа РТиУ: {e}")
            raise
    
    @mcp.tool
    async def get_cache_info() -> Dict[str, Any]:
        """Получить информацию о состоянии кэша метаданных."""
        try:
            logger.info("Получение информации о кэше")
            return client.get_cache_info()
            
        except Exception as e:
            logger.error(f"Ошибка при получении информации о кэше: {e}")
            raise
    
    @mcp.tool
    async def clear_metadata_cache() -> Dict[str, bool]:
        """Очистить кэш метаданных."""
        try:
            logger.info("Очистка кэша метаданных")
            client.clear_metadata_cache()
            return {"success": True}
            
        except Exception as e:
            logger.error(f"Ошибка при очистке кэша: {e}")
            raise
    
    @mcp.tool
    async def list_cached_data() -> Dict[str, Any]:
        """Получить список всех сохраненных данных в JSON файлах."""
        try:
            logger.info("Получение списка кэшированных данных")
            cached_files = client._cache.list_cached_data()
            
            return {
                "status": "success",
                "message": f"Найдено {len(cached_files)} файлов с данными",
                "files_count": len(cached_files),
                "files": cached_files
            }
            
        except Exception as e:
            logger.error(f"Ошибка при получении списка данных: {e}")
            return {
                "status": "error",
                "message": f"Ошибка при получении списка данных: {str(e)}"
            }
    
    @mcp.tool
    async def filter_local_data(
        file_name: str,
        filters: Optional[Dict[str, Any]] = None,
        select_fields: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        sort_by: Optional[str] = None,
        sort_desc: bool = False
    ) -> Dict[str, Any]:
        """Фильтровать данные из локального JSON файла без обращения к 1С."""
        try:
            logger.info(f"Фильтрация локальных данных из файла {file_name}")
            
            result = client._cache.filter_local_data(
                file_name=file_name,
                filters=filters,
                select_fields=select_fields,
                limit=limit,
                offset=offset,
                sort_by=sort_by,
                sort_desc=sort_desc
            )
            
            return {
                "status": "success",
                "message": f"Данные отфильтрованы: {result['returned_count']} из {result['total_count']} записей",
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Ошибка при фильтрации локальных данных: {e}")
            return {
                "status": "error",
                "message": f"Ошибка при фильтрации данных: {str(e)}"
            }
    
    @mcp.tool
    async def count_local_data(
        file_name: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Подсчитать записи в локальном JSON файле."""
        try:
            logger.info(f"Подсчет записей в файле {file_name}")
            
            result = client._cache.count_local_data(file_name=file_name, filters=filters)
            
            return {
                "status": "success",
                "message": f"Подсчет завершен: {result['filtered_count']} из {result['total_count']} записей",
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Ошибка при подсчете локальных данных: {e}")
            return {
                "status": "error",
                "message": f"Ошибка при подсчете данных: {str(e)}"
            }
    
    @mcp.tool
    async def get_file_structure(file_name: str) -> Dict[str, Any]:
        """Получить структуру JSON файла с данными (поля, типы, примеры значений)."""
        try:
            logger.info(f"Анализ структуры файла {file_name}")
            
            result = client._cache.get_file_structure(file_name=file_name)
            
            return {
                "status": "success",
                "message": f"Структура файла проанализирована: {result['field_count']} полей",
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Ошибка при анализе структуры файла: {e}")
            return {
                "status": "error",
                "message": f"Ошибка при анализе структуры файла: {str(e)}"
            }
    
    @mcp.tool
    async def create_1c_entity(
        entity_set: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Создать новую сущность в 1С."""
        try:
            logger.info(f"Создание сущности в {entity_set}")
            
            # Добавляем системные поля если их нет
            entity_data = data.copy()
            
            # Для справочников добавляем обязательные поля
            if "Catalog_" in entity_set:
                if "Code" not in entity_data:
                    entity_data["Code"] = ""
                if "Description" not in entity_data:
                    entity_data["Description"] = entity_data.get("Code", "Новый элемент")
            
            # Для документов добавляем дату если её нет
            if "Document_" in entity_set:
                if "Date" not in entity_data:
                    entity_data["Date"] = datetime.now().isoformat()
                if "Posted" not in entity_data:
                    entity_data["Posted"] = False
            
            result = await client.create_entity(entity_set, entity_data)
            
            logger.info("Сущность успешно создана")
            return {
                "status": "success",
                "message": f"Сущность успешно создана в {entity_set}",
                "entity_set": entity_set,
                "created_entity": result
            }
            
        except Exception as e:
            logger.error(f"Ошибка при создании сущности: {e}")
            return {
                "status": "error",
                "message": f"Ошибка при создании сущности: {str(e)}"
            }
    
    @mcp.tool
    async def update_1c_entity(
        entity_set: str,
        entity_key: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Обновить существующую сущность в 1С."""
        try:
            logger.info(f"Обновление сущности {entity_key} в {entity_set}")
            
            result = await client.update_entity(entity_set, entity_key, data)
            
            logger.info("Сущность успешно обновлена")
            return {
                "status": "success",
                "message": f"Сущность {entity_key} успешно обновлена в {entity_set}",
                "entity_set": entity_set,
                "entity_key": entity_key,
                "updated_data": data,
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении сущности: {e}")
            return {
                "status": "error",
                "message": f"Ошибка при обновлении сущности: {str(e)}"
            }
    
    @mcp.tool
    async def clear_data_cache() -> Dict[str, bool]:
        """Очистить все сохраненные данные запросов."""
        try:
            logger.info("Очистка кэша данных")
            client._cache.clear_data_cache()
            return {
                "status": "success",
                "message": "Кэш данных очищен"
            }
            
        except Exception as e:
            logger.error(f"Ошибка при очистке кэша данных: {e}")
            return {
                "status": "error",
                "message": f"Ошибка при очистке кэша данных: {str(e)}"
            }
    
    return mcp
