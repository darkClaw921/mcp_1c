"""Модуль для кэширования данных 1С."""

import json
import os
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loguru import logger


class DataCache:
    """Кэш для данных 1С."""
    
    def __init__(self, cache_dir: str = "cache", cache_ttl_hours: int = 24):
        """
        Инициализация кэша.
        
        Args:
            cache_dir: Директория для хранения кэша
            cache_ttl_hours: Время жизни кэша в часах
        """
        self.cache_dir = Path(cache_dir)
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.metadata_file = self.cache_dir / "metadata.json"
        self.metadata_info_file = self.cache_dir / "metadata_info.json"
        self.data_dir = self.cache_dir / "data"
        
        # Создаем директории кэша если их нет
        self.cache_dir.mkdir(exist_ok=True)
        self.data_dir.mkdir(exist_ok=True)
        
        logger.info(f"Инициализация кэша данных в {self.cache_dir}")
    
    def _is_cache_valid(self, file_path: Path) -> bool:
        """Проверить актуальность кэша."""
        if not file_path.exists():
            return False
        
        # Проверяем время модификации файла
        file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
        return datetime.now() - file_time < self.cache_ttl
    
    def _find_data_file(self, file_name: str) -> Path:
        """Найти файл данных по имени или частичному совпадению."""
        file_path = self.data_dir / file_name
        
        # Если файл найден по точному имени, возвращаем его
        if file_path.exists():
            return file_path
        
        # Убираем расширение .json из поискового запроса если оно есть
        search_name = file_name
        if search_name.endswith('.json'):
            search_name = search_name[:-5]  # Убираем '.json'
        
        # Ищем файлы, которые начинаются с указанного имени
        matching_files = list(self.data_dir.glob(f"{search_name}*"))
        
        if not matching_files:
            # Ищем файлы, которые содержат указанное имя (без .json)
            matching_files = [f for f in self.data_dir.glob("*.json") if search_name in f.name]
        
        if not matching_files:
            raise FileNotFoundError(f"Файл данных не найден: {file_name}")
        elif len(matching_files) == 1:
            file_path = matching_files[0]
            logger.info(f"Найден файл по частичному совпадению: {file_path.name}")
            return file_path
        else:
            # Если найдено несколько файлов, выбираем самый новый
            file_path = max(matching_files, key=lambda f: f.stat().st_mtime)
            logger.info(f"Найдено {len(matching_files)} файлов, выбран самый новый: {file_path.name}")
            return file_path
    
    def get_raw_metadata(self) -> Optional[Dict[str, Any]]:
        """Получить сырые метаданные из кэша."""
        if not self._is_cache_valid(self.metadata_file):
            logger.debug("Кэш сырых метаданных устарел или отсутствует")
            return None
        
        try:
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            logger.debug("Сырые метаданные загружены из кэша")
            return metadata
            
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Ошибка при чтении кэша сырых метаданных: {e}")
            return None
    
    def save_raw_metadata(self, metadata: Dict[str, Any]) -> None:
        """Сохранить сырые метаданные в кэш."""
        try:
            # Добавляем метаинформацию о времени кэширования
            cache_data = {
                "cached_at": datetime.now().isoformat(),
                "metadata": metadata
            }
            
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Сырые метаданные сохранены в кэш: {self.metadata_file}")
            
        except IOError as e:
            logger.error(f"Ошибка при сохранении сырых метаданных в кэш: {e}")
    
    def get_parsed_metadata(self) -> Optional[Dict[str, Any]]:
        """Получить обработанные метаданные из кэша."""
        if not self._is_cache_valid(self.metadata_info_file):
            logger.debug("Кэш обработанных метаданных устарел или отсутствует")
            return None
        
        try:
            with open(self.metadata_info_file, 'r', encoding='utf-8') as f:
                metadata_info = json.load(f)
            
            logger.debug("Обработанные метаданные загружены из кэша")
            return metadata_info
            
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Ошибка при чтении кэша обработанных метаданных: {e}")
            return None
    
    def save_parsed_metadata(self, metadata_info: Dict[str, Any]) -> None:
        """Сохранить обработанные метаданные в кэш."""
        try:
            # Добавляем метаинформацию о времени кэширования
            cache_data = {
                "cached_at": datetime.now().isoformat(),
                "metadata_info": metadata_info
            }
            
            with open(self.metadata_info_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Обработанные метаданные сохранены в кэш: {self.metadata_info_file}")
            
        except IOError as e:
            logger.error(f"Ошибка при сохранении обработанных метаданных в кэш: {e}")
    
    def clear_cache(self) -> None:
        """Очистить кэш метаданных."""
        try:
            if self.metadata_file.exists():
                self.metadata_file.unlink()
                logger.info("Кэш сырых метаданных очищен")
            
            if self.metadata_info_file.exists():
                self.metadata_info_file.unlink()
                logger.info("Кэш обработанных метаданных очищен")
                
        except IOError as e:
            logger.error(f"Ошибка при очистке кэша: {e}")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Получить информацию о состоянии кэша."""
        info = {
            "cache_dir": str(self.cache_dir),
            "cache_ttl_hours": self.cache_ttl.total_seconds() / 3600,
            "raw_metadata": {
                "exists": self.metadata_file.exists(),
                "valid": self._is_cache_valid(self.metadata_file),
                "size_bytes": self.metadata_file.stat().st_size if self.metadata_file.exists() else 0,
                "modified_at": datetime.fromtimestamp(self.metadata_file.stat().st_mtime).isoformat() 
                              if self.metadata_file.exists() else None
            },
            "parsed_metadata": {
                "exists": self.metadata_info_file.exists(),
                "valid": self._is_cache_valid(self.metadata_info_file),
                "size_bytes": self.metadata_info_file.stat().st_size if self.metadata_info_file.exists() else 0,
                "modified_at": datetime.fromtimestamp(self.metadata_info_file.stat().st_mtime).isoformat()
                              if self.metadata_info_file.exists() else None
            }
        }
        
        return info
    
    def _generate_query_hash(self, entity_set: str, params: Dict[str, Any]) -> str:
        """Генерировать хеш для запроса данных."""
        query_key = f"{entity_set}_{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(query_key.encode()).hexdigest()
    
    def save_query_data(self, entity_set: str, params: Dict[str, Any], data: List[Dict[str, Any]]) -> str:
        """Сохранить данные запроса в кэш."""
        try:
            query_hash = self._generate_query_hash(entity_set, params)
            file_path = self.data_dir / f"{entity_set}_{query_hash}.json"
            
            cache_data = {
                "cached_at": datetime.now().isoformat(),
                "entity_set": entity_set,
                "query_params": params,
                "record_count": len(data),
                "data": data
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Данные запроса сохранены: {file_path} ({len(data)} записей)")
            return str(file_path)
            
        except IOError as e:
            logger.error(f"Ошибка при сохранении данных запроса: {e}")
            raise
    
    def get_query_data(self, entity_set: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Получить данные запроса из кэша."""
        try:
            query_hash = self._generate_query_hash(entity_set, params)
            file_path = self.data_dir / f"{entity_set}_{query_hash}.json"
            
            if not self._is_cache_valid(file_path):
                logger.debug(f"Кэш данных запроса устарел или отсутствует: {file_path}")
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            
            logger.debug(f"Данные запроса загружены из кэша: {file_path}")
            return cached_data
            
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Ошибка при чтении кэша данных запроса: {e}")
            return None
    
    def list_cached_data(self) -> List[Dict[str, Any]]:
        """Получить список всех закэшированных данных."""
        cached_files = []
        
        try:
            for file_path in self.data_dir.glob("*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    file_info = {
                        "file_name": file_path.name,
                        "entity_set": data.get("entity_set", "unknown"),
                        "cached_at": data.get("cached_at"),
                        "record_count": data.get("record_count", 0),
                        "query_params": data.get("query_params", {}),
                        "file_size_bytes": file_path.stat().st_size,
                        "is_valid": self._is_cache_valid(file_path)
                    }
                    cached_files.append(file_info)
                    
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Ошибка при чтении файла {file_path}: {e}")
                    continue
            
            logger.debug(f"Найдено {len(cached_files)} файлов с данными")
            return cached_files
            
        except Exception as e:
            logger.error(f"Ошибка при получении списка кэшированных данных: {e}")
            return []
    
    def filter_local_data(
        self, 
        file_name: str, 
        filters: Optional[Dict[str, Any]] = None,
        select_fields: Optional[List[str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        sort_by: Optional[str] = None,
        sort_desc: bool = False
    ) -> Dict[str, Any]:
        """Фильтровать локальные данные без обращения к 1С."""
        try:
            file_path = self._find_data_file(file_name)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            
            data = cached_data.get("data", [])
            
            # Применяем фильтры
            if filters:
                filtered_data = []
                for record in data:
                    match = True
                    for field, value in filters.items():
                        if field not in record:
                            match = False
                            break
                        
                        # Простая фильтрация по равенству или содержанию
                        if isinstance(value, str) and isinstance(record[field], str):
                            if value.lower() not in record[field].lower():
                                match = False
                                break
                        elif record[field] != value:
                            match = False
                            break
                    
                    if match:
                        filtered_data.append(record)
                
                data = filtered_data
            
            # Применяем сортировку
            if sort_by and data:
                try:
                    # Проверяем, что поле для сортировки существует в данных
                    if sort_by in data[0]:
                        def sort_key(record):
                            value = record.get(sort_by)
                            # Обрабатываем None значения
                            if value is None:
                                return "" if isinstance(data[0].get(sort_by), str) else 0
                            return value
                        
                        data = sorted(data, key=sort_key, reverse=sort_desc)
                        logger.debug(f"Данные отсортированы по полю '{sort_by}', убывание: {sort_desc}")
                    else:
                        logger.warning(f"Поле для сортировки '{sort_by}' не найдено в данных")
                except Exception as e:
                    logger.warning(f"Ошибка при сортировке по полю '{sort_by}': {e}")
            
            # Применяем выборку полей
            if select_fields:
                selected_data = []
                for record in data:
                    selected_record = {}
                    for field in select_fields:
                        if field in record:
                            selected_record[field] = record[field]
                    selected_data.append(selected_record)
                data = selected_data
            
            # Применяем пагинацию
            total_count = len(data)
            if offset:
                data = data[offset:]
            if limit:
                data = data[:limit]
            
            result = {
                "requested_file_name": file_name,
                "actual_file_name": file_path.name,
                "entity_set": cached_data.get("entity_set", "unknown"),
                "total_count": total_count,
                "returned_count": len(data),
                "filters_applied": filters or {},
                "fields_selected": select_fields or [],
                "sort_by": sort_by,
                "sort_desc": sort_desc,
                "data": data
            }
            
            logger.info(f"Локальная фильтрация: {total_count} -> {len(data)} записей")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при фильтрации локальных данных: {e}")
            raise
    
    def count_local_data(self, file_name: str, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Подсчитать записи в локальных данных."""
        try:
            file_path = self._find_data_file(file_name)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            
            data = cached_data.get("data", [])
            total_count = len(data)
            
            # Применяем фильтры для подсчета
            if filters:
                filtered_count = 0
                for record in data:
                    match = True
                    for field, value in filters.items():
                        if field not in record:
                            match = False
                            break
                        
                        if isinstance(value, str) and isinstance(record[field], str):
                            if value.lower() not in record[field].lower():
                                match = False
                                break
                        elif record[field] != value:
                            match = False
                            break
                    
                    if match:
                        filtered_count += 1
                
                filtered_count = filtered_count
            else:
                filtered_count = total_count
            
            result = {
                "requested_file_name": file_name,
                "actual_file_name": file_path.name,
                "entity_set": cached_data.get("entity_set", "unknown"),
                "total_count": total_count,
                "filtered_count": filtered_count,
                "filters_applied": filters or {}
            }
            
            logger.info(f"Подсчет записей: {filtered_count} из {total_count}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при подсчете локальных данных: {e}")
            raise
    
    def clear_data_cache(self) -> None:
        """Очистить кэш данных запросов."""
        try:
            for file_path in self.data_dir.glob("*.json"):
                file_path.unlink()
            
            logger.info("Кэш данных запросов очищен")
            
        except IOError as e:
            logger.error(f"Ошибка при очистке кэша данных: {e}")
    
    def get_file_structure(self, file_name: str) -> Dict[str, Any]:
        """Получить структуру JSON файла с данными."""
        try:
            file_path = self._find_data_file(file_name)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            
            data = cached_data.get("data", [])
            
            if not data:
                return {
                    "file_name": file_name,
                    "entity_set": cached_data.get("entity_set", "unknown"),
                    "record_count": 0,
                    "structure": {},
                    "sample_values": {}
                }
            
            # Анализируем структуру данных
            structure = {}
            sample_values = {}
            
            # Берем первые несколько записей для анализа типов
            sample_size = min(10, len(data))
            sample_records = data[:sample_size]
            
            # Собираем все уникальные поля
            all_fields = set()
            for record in sample_records:
                all_fields.update(record.keys())
            
            # Анализируем каждое поле
            for field in all_fields:
                field_types = set()
                field_samples = []
                null_count = 0
                
                for record in sample_records:
                    value = record.get(field)
                    if value is None:
                        null_count += 1
                    else:
                        field_types.add(type(value).__name__)
                        if len(field_samples) < 3:  # Берем до 3 примеров
                            field_samples.append(value)
                
                # Определяем основной тип поля
                if len(field_types) == 1:
                    primary_type = list(field_types)[0]
                elif len(field_types) > 1:
                    primary_type = "mixed"
                else:
                    primary_type = "null"
                
                structure[field] = {
                    "type": primary_type,
                    "nullable": null_count > 0,
                    "null_count": null_count,
                    "sample_count": sample_size - null_count
                }
                
                sample_values[field] = field_samples[:3]  # Максимум 3 примера
            
            result = {
                "requested_file_name": file_name,
                "actual_file_name": file_path.name,
                "entity_set": cached_data.get("entity_set", "unknown"),
                "cached_at": cached_data.get("cached_at"),
                "total_record_count": cached_data.get("record_count", len(data)),
                "analyzed_records": sample_size,
                "field_count": len(all_fields),
                "structure": structure,
                "sample_values": sample_values
            }
            
            logger.info(f"Структура файла проанализирована: {len(all_fields)} полей, {sample_size} записей")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при анализе структуры файла: {e}")
            raise


# Для обратной совместимости
MetadataCache = DataCache
