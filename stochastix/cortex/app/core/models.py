from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from cortex.app.core.database import Base


class PredictionAudit(Base):
    __tablename__ = "prediction_audits"

    # One audit row per pair per target date. The endpoint also checks
    # before insert, but only this constraint makes concurrent requests
    # safe. Existing databases need a one-off ALTER TABLE — see
    # README-DEPLOYMENT.md, "Database migration".
    __table_args__ = (
        UniqueConstraint("currency_pair", "target_date", name="uq_audit_pair_target"),
    )

    id = Column(Integer, primary_key=True, index=True)
    currency_pair = Column(String, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    target_date = Column(Date, index=True)

    predicted_rate = Column(Float)
    predicted_change_pct = Column(Float)

    actual_rate = Column(Float, nullable=True)
    actual_change_pct = Column(Float, nullable=True)

    trust_label = Column(String, nullable=True)
    is_resolved = Column(Boolean, default=False)
