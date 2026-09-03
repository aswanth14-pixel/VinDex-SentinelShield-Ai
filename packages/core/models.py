from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Dispute(Base):
    __tablename__ = "disputes"

    id = Column(String, primary_key=True)
    payment_id = Column(String, nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    currency = Column(String, default="INR")
    status = Column(String, nullable=False)
    reason_code = Column(String, nullable=False)
    respond_by = Column(Integer, nullable=False)
    created_at = Column(Integer, nullable=False)
    created_timestamp = Column(DateTime, default=datetime.utcnow)

    evidence_binders = relationship("EvidenceBinder", back_populates="dispute")
    evaluations = relationship("Evaluation", back_populates="dispute")
    audit_logs = relationship("AuditLog", back_populates="dispute")


class EvidenceBinder(Base):
    __tablename__ = "evidence_binders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dispute_id = Column(String, ForeignKey("disputes.id"), nullable=False, index=True)
    order_id = Column(String, nullable=False)
    awb_number = Column(String, nullable=True)
    courier_name = Column(String, nullable=True)
    invoice_path = Column(String, nullable=True)
    pod_path = Column(String, nullable=True)

    dispute = relationship("Dispute", back_populates="evidence_binders")
    extraction = relationship("Extraction", back_populates="binder", uselist=False)


class Extraction(Base):
    __tablename__ = "extractions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    binder_id = Column(Integer, ForeignKey("evidence_binders.id"), nullable=False, index=True)
    raw_response = Column(Text, nullable=True)
    parsed_evidence = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)

    binder = relationship("EvidenceBinder", back_populates="extraction")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dispute_id = Column(String, ForeignKey("disputes.id"), nullable=False, index=True)
    win_probability = Column(Float, nullable=False)
    address_similarity = Column(Float, nullable=True)
    contradictions = Column(Text, nullable=True)
    action = Column(String, nullable=False)

    dispute = relationship("Dispute", back_populates="evaluations")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dispute_id = Column(String, ForeignKey("disputes.id"), nullable=True, index=True)
    event_type = Column(String, nullable=False)
    event_data = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    dispute = relationship("Dispute", back_populates="audit_logs")
