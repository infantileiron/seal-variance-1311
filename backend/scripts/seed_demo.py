import random,json
from datetime import datetime,timezone
from sqlalchemy import select,func
from src.config.database import Base,engine,SessionLocal
from src.models.entities import User,Process,Sample,Assessment,Trial
from src.utils.security import hash_password
from src.services.assessments import snapshot_for

def seed():
    Base.metadata.create_all(engine);rng=random.Random(3105)
    with SessionLocal() as db:
        for role in ('admin','analyst','viewer'):
            email=role+'@demo.local'
            if not db.scalar(select(User).where(User.email==email)):db.add(User(email=email,role=role,password_hash=hash_password('Demo123!')))
        db.commit()
        means={}
        for j,(name,temp,dwell,pressure,mean) in enumerate([('稳温基线',160,.8,.32,22.5),('延时封合',160,1.2,.32,25.8),('升温短封',175,.65,.32,24.1)],1):
            code=f'HC-S{j}';process=db.scalar(select(Process).where(Process.code==code))
            if not process:
                process=Process(code=code,name=name,temperature=temp,dwell=dwell,pressure=pressure,note='BOPP/PE复合膜，批号HC-1115，同批独立取样');db.add(process);db.flush()
            means[code]=mean
            for i in range(35):
                code=f'HC-S{j}-{i+1:03}';value=round(max(1,rng.gauss(mean,1.7)),2)
                if not db.scalar(select(Sample).where(Sample.code==code)):db.add(Sample(code=code,process_id=process.id,lot='HC-1115',force=value,flagged=i==0,note='首件标记，保留纳入分析' if i==0 else ''))
        db.commit()
        title='HC-1115 三方案首轮复核'
        if not db.scalar(select(Assessment).where(Assessment.title==title)):
            ids=db.scalars(select(Process.id).where(Process.code.in_(['HC-S1','HC-S2','HC-S3'])).order_by(Process.id)).all()
            db.add(Assessment(title=title,lot='HC-1115',snapshot=snapshot_for(db,ids,'HC-1115'),status='queued',created_at=datetime.now(timezone.utc).isoformat()));db.commit()
        trial_title='HC-1115 三方案分阶段淘汰试验'
        if not db.scalar(select(Trial).where(Trial.title==trial_title)):
            from src.services import trials as trial_service
            from src.schemas.business import TrialInput,ReportInput
            ids=list(db.scalars(select(Process.id).where(Process.code.in_(['HC-S1','HC-S2','HC-S3'])).order_by(Process.id)).all())
            trial=trial_service.create(db,TrialInput(title=trial_title,lot='HC-1115',stage_size=3,budget=36,alpha=0.05,process_ids=ids),'seed')
            for order in trial['orders']:
                trial_service.claim(db,order['id'],'analyst@demo.local')
                value=round(max(1,rng.gauss(means[order['process_code']],1.7)),2)
                trial_service.report(db,order['id'],ReportInput(force=value),'analyst@demo.local')
        counts={t.__tablename__:db.scalar(select(func.count()).select_from(t)) for t in [User,Process,Sample,Assessment,Trial]};print(json.dumps(counts));return counts
if __name__=='__main__':seed()
