#!/usr/bin/env python3
"""
SQLAlchemy ORM Models for Thesis Database
PostgreSQL schema mapped to Python classes
"""

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, JSON, ARRAY, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

Base = declarative_base()

# ============================================================
# CORE MODELS
# ============================================================

class User(Base):
    """Student/User profile"""
    __tablename__ = "users"
    
    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    detail_level = Column(Integer, default=1)
    language = Column(String(10), default='en')
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    sessions = relationship("Session", back_populates="user")
    events = relationship("Event", back_populates="user")
    decisions = relationship("AiDecisionLog", back_populates="user")
    episodes = relationship("RlEpisode", back_populates="user")

class Session(Base):
    """Learning session"""
    __tablename__ = "sessions"
    
    session_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="sessions")
    events = relationship("Event", back_populates="session")
    decisions = relationship("AiDecisionLog", back_populates="session")
    episodes = relationship("RlEpisode", back_populates="session")

class Event(Base):
    """AR/Game interaction event"""
    __tablename__ = "events"
    __table_args__ = (
        Index('idx_events_session', 'session_id', 'scene_name'),
    )
    
    event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.session_id"), nullable=False)
    scene_name = Column(String(255), nullable=False)
    event_type = Column(String(100), nullable=False)  # quiz_answer, ar_interaction, etc.
    object_id = Column(String(255), nullable=True)
    module_id = Column(String(255), ForeignKey("modules.module_id"), nullable=True)
    correct = Column(Boolean, nullable=True)
    time_spent_ms = Column(Integer, nullable=True)
    payload = Column(JSONB, default={})
    client_timestamp = Column(DateTime, nullable=False)
    server_timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="events")
    session = relationship("Session", back_populates="events")
    module = relationship("Module", back_populates="events")

class Module(Base):
    """AR content module"""
    __tablename__ = "modules"
    
    module_id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    scene_name = Column(String(255), nullable=False)
    cdn_bundle_url = Column(String(500), nullable=False)
    difficulty = Column(Integer, default=1)
    config = Column(JSONB, default={})
    
    # Relationships
    events = relationship("Event", back_populates="module")
    chunks = relationship("DocumentChunk", back_populates="module")

class DocumentChunk(Base):
    """DNA curriculum chunk with embedding"""
    __tablename__ = "document_chunks"
    
    chunk_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_id = Column(String(255), ForeignKey("modules.module_id"), nullable=False)
    source_doc = Column(String(255), nullable=False)
    chunk_text = Column(Text, nullable=False)
    embedding = Column(ARRAY(Float), nullable=True)  # 384-dim embedding
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    module = relationship("Module", back_populates="chunks")

class AiDecisionLog(Base):
    """AI decision audit trail"""
    __tablename__ = "ai_decision_log"
    
    decision_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.session_id"), nullable=False)
    question = Column(String(1000), nullable=False)
    is_on_topic = Column(Boolean, nullable=False)
    topic_similarity = Column(Float, default=0.0)
    retrieved_chunks = Column(Integer, default=0)
    llm_response = Column(Text, nullable=True)
    llm_confidence = Column(Float, default=0.0)
    latency_ms = Column(Float, nullable=False)
    action_id = Column(Integer, nullable=True)
    action_name = Column(String(100), nullable=True)
    recommended_difficulty = Column(Integer, nullable=True)
    recommended_topic = Column(String(255), nullable=True)
    reward = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="decisions")
    session = relationship("Session", back_populates="decisions")

class RlEpisode(Base):
    """RL training episode"""
    __tablename__ = "rl_episodes"
    
    episode_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.session_id"), nullable=False)
    state_vector = Column(ARRAY(Float), nullable=True)  # 8D state
    action_id = Column(Integer, nullable=False)
    reward = Column(Float, nullable=False)
    next_state_vector = Column(ARRAY(Float), nullable=True)
    done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="episodes")
    session = relationship("Session", back_populates="episodes")

class Experiment(Base):
    """Experiment tracking (MLflow integration)"""
    __tablename__ = "experiments"
    
    experiment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    baseline_accuracy = Column(Float, nullable=True)
    adaptive_accuracy = Column(Float, nullable=True)
    improvement_percent = Column(Float, nullable=True)
    num_users = Column(Integer, default=0)
    num_interactions = Column(Integer, default=0)
    avg_latency_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
