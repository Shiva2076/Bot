import logging
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.paper_signal import PaperSignalRecord
from schemas.paper_engine import (
    PaperExecutionStatus,
    PaperSignalCreate,
    PaperSignalEligibility,
    PaperSignalEventRecord,
)

logger = logging.getLogger(__name__)


class SignalAuditPersistenceError(Exception):
    """Raised when writing or updating a signal audit record fails."""
    pass


class SignalNotFoundError(Exception):
    """Raised when a requested paper signal record is not found."""
    pass


class PaperSignalRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, data: PaperSignalCreate) -> PaperSignalRecord:
        try:
            record = PaperSignalRecord(
                signal_uuid=data.signal_uuid,
                session_date=data.session_date,
                generated_at=data.generated_at,
                underlying=data.underlying.value if hasattr(data.underlying, "value") else str(data.underlying),
                strategy=data.strategy,
                direction=data.direction.value if hasattr(data.direction, "value") else str(data.direction),
                score=data.score,
                raw_score=data.raw_score,
                signal_score=data.signal_score,
                confidence=data.confidence,
                scorer_version=data.scorer_version,
                spot_level=data.spot_level,
                contract_symbol=data.contract_symbol,
                contract_strike=data.contract_strike,
                contract_expiry=data.contract_expiry,
                contract_option_type=data.contract_option_type.value if hasattr(data.contract_option_type, "value") else data.contract_option_type,
                entry_premium=data.entry_premium,
                stop_loss=data.stop_loss,
                target=data.target,
                quote_ltp=data.quote_ltp,
                quote_bid=data.quote_bid,
                quote_ask=data.quote_ask,
                quote_volume=data.quote_volume,
                quote_oi=data.quote_oi,
                quote_exchange_timestamp=data.quote_exchange_timestamp,
                quote_provider=data.quote_provider,
                quote_freshness=data.quote_freshness.value if hasattr(data.quote_freshness, "value") else data.quote_freshness,
                gate_reason=data.gate_reason.value if hasattr(data.gate_reason, "value") else data.gate_reason,
                premarket_action=data.premarket_action.value if hasattr(data.premarket_action, "value") else data.premarket_action,
                premarket_wait_trigger=data.premarket_wait_trigger,
                freshness_diagnostics=data.freshness_diagnostics,
                eligibility_status=data.eligibility_status.value if hasattr(data.eligibility_status, "value") else str(data.eligibility_status),
                execution_status=data.execution_status.value if hasattr(data.execution_status, "value") else str(data.execution_status),
                rejection_reasons=list(data.rejection_reasons),
                trade_id=data.trade_id,
                prediction_snapshot=data.prediction_snapshot,
                events=[e.model_dump(mode="json") if hasattr(e, "model_dump") else e for e in data.events],
            )
            self._session.add(record)
            await self._session.flush()
            return record
        except Exception as exc:
            logger.error(f"Failed to persist paper signal audit record {data.signal_uuid}: {exc}")
            raise SignalAuditPersistenceError(
                f"Failed to persist paper signal audit record {data.signal_uuid}: {exc}"
            ) from exc

    async def get(self, signal_id: int) -> PaperSignalRecord:
        record = await self._session.get(PaperSignalRecord, signal_id)
        if record is None:
            raise SignalNotFoundError(f"Paper signal with ID {signal_id} not found")
        return record

    async def get_by_uuid(self, signal_uuid: str) -> Optional[PaperSignalRecord]:
        result = await self._session.execute(
            select(PaperSignalRecord).where(PaperSignalRecord.signal_uuid == signal_uuid)
        )
        return result.scalars().first()

    async def link_trade(
        self,
        signal_id: int,
        trade_id: int,
        event: Optional[PaperSignalEventRecord] = None,
    ) -> PaperSignalRecord:
        try:
            record = await self.get(signal_id)
            record.trade_id = trade_id
            record.execution_status = PaperExecutionStatus.EXECUTED.value
            if event is not None:
                events = list(record.events or [])
                events.append(event.model_dump(mode="json"))
                record.events = events
            await self._session.flush()
            return record
        except SignalNotFoundError:
            raise
        except Exception as exc:
            logger.error(f"Failed to link trade {trade_id} to signal {signal_id}: {exc}")
            raise SignalAuditPersistenceError(
                f"Failed to link trade {trade_id} to signal {signal_id}: {exc}"
            ) from exc

    async def append_event(
        self,
        signal_id: int,
        event: PaperSignalEventRecord,
    ) -> PaperSignalRecord:
        try:
            record = await self.get(signal_id)
            events = list(record.events or [])
            events.append(event.model_dump(mode="json"))
            record.events = events
            await self._session.flush()
            return record
        except SignalNotFoundError:
            raise
        except Exception as exc:
            logger.error(f"Failed to append event to signal {signal_id}: {exc}")
            raise SignalAuditPersistenceError(
                f"Failed to append event to signal {signal_id}: {exc}"
            ) from exc

    async def update_status(
        self,
        signal_id: int,
        eligibility_status: Optional[PaperSignalEligibility] = None,
        execution_status: Optional[PaperExecutionStatus] = None,
        rejection_reasons: Optional[List[str]] = None,
        trade_id: Optional[int] = None,
        event: Optional[PaperSignalEventRecord] = None,
    ) -> PaperSignalRecord:
        try:
            record = await self.get(signal_id)
            if eligibility_status is not None:
                record.eligibility_status = eligibility_status.value
            if execution_status is not None:
                record.execution_status = execution_status.value
            if rejection_reasons is not None:
                record.rejection_reasons = list(rejection_reasons)
            if trade_id is not None:
                record.trade_id = trade_id
            if event is not None:
                events = list(record.events or [])
                events.append(event.model_dump(mode="json"))
                record.events = events
            await self._session.flush()
            return record
        except SignalNotFoundError:
            raise
        except Exception as exc:
            logger.error(f"Failed to update status for signal {signal_id}: {exc}")
            raise SignalAuditPersistenceError(
                f"Failed to update status for signal {signal_id}: {exc}"
            ) from exc

    async def list_for_session(
        self,
        underlying: Optional[str] = None,
        session_date: Optional[date] = None,
        limit: int = 100,
    ) -> List[PaperSignalRecord]:
        query = select(PaperSignalRecord)
        if session_date is not None:
            query = query.where(PaperSignalRecord.session_date == session_date)
        if underlying is not None:
            query = query.where(PaperSignalRecord.underlying == underlying)
        query = query.order_by(PaperSignalRecord.generated_at.desc()).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def count_eligibility_by_session(self, session_date: date) -> Dict[str, int]:
        query = (
            select(PaperSignalRecord.eligibility_status, func.count(PaperSignalRecord.id))
            .where(PaperSignalRecord.session_date == session_date)
            .group_by(PaperSignalRecord.eligibility_status)
        )
        result = await self._session.execute(query)
        return {status: count for status, count in result.all()}
