from sqlalchemy import String,Float,Boolean,Integer,ForeignKey,JSON,Text
from sqlalchemy.orm import Mapped,mapped_column
from src.config.database import Base
class User(Base):
    __tablename__='users'
    id:Mapped[int]=mapped_column(primary_key=True)
    email:Mapped[str]=mapped_column(String(120),unique=True)
    role:Mapped[str]=mapped_column(String(20))
    password_hash:Mapped[str]=mapped_column(String(200))
class Process(Base):
    __tablename__='processes'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(50),unique=True)
    name:Mapped[str]=mapped_column(String(100))
    temperature:Mapped[float]=mapped_column(Float)
    dwell:Mapped[float]=mapped_column(Float)
    pressure:Mapped[float]=mapped_column(Float)
    note:Mapped[str]=mapped_column(Text,default='')
class Sample(Base):
    __tablename__='samples'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(50),unique=True)
    process_id:Mapped[int]=mapped_column(ForeignKey('processes.id'))
    lot:Mapped[str]=mapped_column(String(60))
    force:Mapped[float]=mapped_column(Float)
    flagged:Mapped[bool]=mapped_column(Boolean,default=False)
    note:Mapped[str]=mapped_column(Text,default='')
class Assessment(Base):
    __tablename__='assessments'
    id:Mapped[int]=mapped_column(primary_key=True)
    title:Mapped[str]=mapped_column(String(120),unique=True)
    lot:Mapped[str]=mapped_column(String(60),default='全部')
    status:Mapped[str]=mapped_column(String(20),default='queued')
    snapshot:Mapped[dict]=mapped_column(JSON)
    result:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    error:Mapped[str]=mapped_column(Text,default='')
    recommendation:Mapped[str]=mapped_column(Text,default='')
    selected_process_id:Mapped[int|None]=mapped_column(ForeignKey('processes.id'),nullable=True)
    approved:Mapped[bool]=mapped_column(Boolean,default=False)
    approved_by:Mapped[str]=mapped_column(String(120),default='')
    created_at:Mapped[str]=mapped_column(String(40))
class Audit(Base):
    __tablename__='audit_logs'
    id:Mapped[int]=mapped_column(primary_key=True)
    actor:Mapped[str]=mapped_column(String(120))
    action:Mapped[str]=mapped_column(String(200))
    status:Mapped[int]=mapped_column(Integer)
    created_at:Mapped[str]=mapped_column(String(40))
class Trial(Base):
    __tablename__='trials'
    id:Mapped[int]=mapped_column(primary_key=True)
    title:Mapped[str]=mapped_column(String(120),unique=True)
    lot:Mapped[str]=mapped_column(String(60))
    stage_size:Mapped[int]=mapped_column(Integer)
    budget:Mapped[int]=mapped_column(Integer)
    alpha:Mapped[float]=mapped_column(Float)
    max_stages:Mapped[int]=mapped_column(Integer)
    current_stage:Mapped[int]=mapped_column(Integer,default=1)
    status:Mapped[str]=mapped_column(String(20),default='active')
    finish_reason:Mapped[str]=mapped_column(Text,default='')
    created_at:Mapped[str]=mapped_column(String(40))
class TrialProcess(Base):
    __tablename__='trial_processes'
    id:Mapped[int]=mapped_column(primary_key=True)
    trial_id:Mapped[int]=mapped_column(ForeignKey('trials.id'))
    process_id:Mapped[int]=mapped_column(ForeignKey('processes.id'))
    status:Mapped[str]=mapped_column(String(20),default='alive')
    eliminated_stage:Mapped[int|None]=mapped_column(Integer,nullable=True)
    rationale:Mapped[str]=mapped_column(Text,default='')
class TrialStage(Base):
    __tablename__='trial_stages'
    id:Mapped[int]=mapped_column(primary_key=True)
    trial_id:Mapped[int]=mapped_column(ForeignKey('trials.id'))
    stage_no:Mapped[int]=mapped_column(Integer)
    status:Mapped[str]=mapped_column(String(20),default='open')
    z_bound:Mapped[float]=mapped_column(Float)
    test_alpha:Mapped[float]=mapped_column(Float)
    decisions:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    sealed_at:Mapped[str]=mapped_column(String(40),default='')
class TrialOrder(Base):
    __tablename__='trial_orders'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(60),unique=True)
    trial_id:Mapped[int]=mapped_column(ForeignKey('trials.id'))
    stage_no:Mapped[int]=mapped_column(Integer)
    process_id:Mapped[int]=mapped_column(ForeignKey('processes.id'))
    status:Mapped[str]=mapped_column(String(20),default='issued')
    claimed_by:Mapped[str]=mapped_column(String(120),default='')
    claimed_at:Mapped[str]=mapped_column(String(40),default='')
    reported_at:Mapped[str]=mapped_column(String(40),default='')
    sample_id:Mapped[int|None]=mapped_column(ForeignKey('samples.id'),nullable=True)
