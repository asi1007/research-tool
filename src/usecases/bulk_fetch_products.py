from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.domain.value_objects.asin import Asin
from src.infrastructure.column_mapper import ColumnMapper
from src.infrastructure.sheet_repository import GoogleSheetRepository, SheetTable
from src.infrastructure.request_pacer import RequestPacer
from src.infrastructure.shipping_calculator import InternationalShippingCalculator
from src.usecases.product_info_fetcher import ProductInfoFetcher
from src.usecases.row_update_planner import RowUpdatePlanner

logger = logging.getLogger(__name__)


@dataclass
class SheetResult:
    sheet_name: str
    total_rows: int = 0
    invalid_asin: int = 0
    already_filled: int = 0
    fetched: int = 0
    updated_cells: int = 0
    failed: list[str] = field(default_factory=list)


class BulkFetchProductsUseCase:
    def __init__(
        self,
        repository: GoogleSheetRepository,
        fetcher: ProductInfoFetcher,
        shipping_calculator: InternationalShippingCalculator,
        overwrite: bool = False,
        dry_run: bool = False,
        interval_seconds: float = 1.0,
        checkpoint_size: int = 25,
    ) -> None:
        self.repository = repository
        self.fetcher = fetcher
        self.shipping_calculator = shipping_calculator
        self.overwrite = overwrite
        self.dry_run = dry_run
        self.pacer = RequestPacer(interval_seconds)
        self.checkpoint_size = checkpoint_size

    def count_targets(self, sheet_name: str) -> SheetResult:
        table = self.repository.read_table(sheet_name)
        mapper = ColumnMapper(table.headers)
        planner = RowUpdatePlanner(mapper, overwrite=self.overwrite)
        result = SheetResult(sheet_name=sheet_name, total_rows=len(table.data_rows))

        asin_column = mapper.column_index("asin")
        if asin_column is None:
            return result

        result.fetched = len(self._collect_targets(table, asin_column, planner, result, None))
        return result

    def execute(self, sheet_name: str, limit: int | None = None) -> SheetResult:
        table = self.repository.read_table(sheet_name)
        mapper = ColumnMapper(table.headers)
        planner = RowUpdatePlanner(mapper, overwrite=self.overwrite)
        result = SheetResult(sheet_name=sheet_name, total_rows=len(table.data_rows))

        asin_column = mapper.column_index("asin")
        if asin_column is None:
            logger.warning("ASIN列が見つからないためスキップ", extra={"context": {"sheet": sheet_name}})
            return result

        targets = self._collect_targets(table, asin_column, planner, result, limit)
        pending = self._fetch_and_plan(targets, planner, result, sheet_name)
        self._flush(sheet_name, pending, result)

        return result

    def _flush(
        self, sheet_name: str, updates: dict[int, dict[int, object]], result: SheetResult
    ) -> None:
        if not updates:
            return

        cells = sum(len(columns) for columns in updates.values())
        if self.dry_run:
            result.updated_cells += cells
            return

        result.updated_cells += self.repository.apply_updates(sheet_name, updates)
        logger.info(
            "シートへ書き込み",
            extra={
                "context": {"sheet": sheet_name, "rows": len(updates), "cells": cells}
            },
        )

    def _collect_targets(
        self,
        table: SheetTable,
        asin_column: int,
        planner: RowUpdatePlanner,
        result: SheetResult,
        limit: int | None,
    ) -> list[tuple[int, list, Asin]]:
        targets: list[tuple[int, list, Asin]] = []

        for index, row in enumerate(table.data_rows):
            raw = row[asin_column] if asin_column < len(row) else ""
            if not str(raw).strip():
                continue

            asin = Asin.parse(raw)
            if asin is None:
                result.invalid_asin += 1
                continue

            if not planner.needs_fetch(row):
                result.already_filled += 1
                continue

            targets.append((table.row_number(index), row, asin))
            if limit is not None and len(targets) >= limit:
                break

        return targets

    def _fetch_and_plan(
        self,
        targets: list[tuple[int, list, Asin]],
        planner: RowUpdatePlanner,
        result: SheetResult,
        sheet_name: str,
    ) -> dict[int, dict[int, object]]:
        updates: dict[int, dict[int, object]] = {}

        for position, (row_number, row, asin) in enumerate(targets):
            self.pacer.wait()
            logger.info(
                "商品情報を取得",
                extra={
                    "context": {
                        "sheet": sheet_name,
                        "row": row_number,
                        "asin": str(asin),
                        "progress": f"{position + 1}/{len(targets)}",
                    }
                },
            )
            try:
                product = self.fetcher.fetch(asin)
            except Exception as error:
                logger.error(
                    "商品情報の取得に失敗",
                    extra={"context": {"sheet": sheet_name, "row": row_number, "asin": str(asin)}},
                    exc_info=error,
                )
                result.failed.append(str(asin))
                continue

            result.fetched += 1
            shipping = self.shipping_calculator.calculate(product.size, product.weight_grams)
            if planned := planner.plan(row, product, shipping):
                updates[row_number] = planned
                logger.debug(
                    "更新内容",
                    extra={
                        "context": {
                            "sheet": sheet_name,
                            "row": row_number,
                            "asin": str(asin),
                            "updates": {
                                planner.mapper.headers[column]: str(value)[:60]
                                for column, value in sorted(planned.items())
                            },
                        }
                    },
                )

            if self.checkpoint_size > 0 and len(updates) >= self.checkpoint_size:
                self._flush(sheet_name, updates, result)
                updates = {}

        return updates
