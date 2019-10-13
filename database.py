# encoding: utf-8
from __future__ import annotations

from typing import Optional, List

import asyncpg

from config import DATABASE_CREDENTIALS, DATABASE_SCHEMA


class DatabaseConnection:
    def __init__(self, pool: asyncpg.pool.Pool):
        self.__pool = pool

    @staticmethod
    async def create() -> DatabaseConnection:
        pool: asyncpg.pool.Pool = await asyncpg.connect(**DATABASE_CREDENTIALS)
        await pool.execute(f"SET search_path TO {DATABASE_SCHEMA}")
        return DatabaseConnection(pool)

    async def update_keys(self, user_id: int, file_id: str, keywords: str, *, replace: bool = True):
        await self.__pool.execute(f'''
            INSERT INTO stickers ( user_id, file_id, keys )
            VALUES ( $1, $2, $3 )
            ON CONFLICT ON CONSTRAINT stickers_pkey
            DO UPDATE
              SET keys = {"$3" if replace else "stickers.keys || $3"}
        ''', user_id, file_id, keywords)

    async def get_keys(self, user_id: int, file_id: str) -> Optional[List[str]]:
        return await self.__pool.fetchval('''
            SELECT keys
            FROM stickers
            WHERE user_id=$1
            AND file_id=$2;
        ''', user_id, file_id)

    async def find_stickers_with_key(self, user_id: int, key: str, *, offset: int = 0) -> List[str]:
        records = await self.__pool.fetch(
            'SELECT file_id FROM stickers WHERE user_id=$1 AND $2 ILIKE ANY(keys) LIMIT 10 OFFSET $3;',
            user_id,
            key,
            offset
        )
        return [record['file_id'] for record in records]
