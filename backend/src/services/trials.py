import time
from datetime import datetime,timezone
from sqlalchemy import select,func,update
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from src.models.entities import Trial,TrialProcess,TrialStage,TrialOrder,Process,Sample
from src.services import sequential
from src.controllers.business import serialize

OCCUPIED=('issued','claimed','reported')

def now():return datetime.now(timezone.utc).isoformat()
def get(db,id):
    trial=db.get(Trial,id)
    if not trial:raise HTTPException(404,'淘汰试验不存在')
    return trial
def occupancy(db,trial_id):
    """试条占用 = 未撤销的测量单数；已领单不可撤回，撤销未领单释放预算。"""
    return db.scalar(select(func.count()).select_from(TrialOrder).where(TrialOrder.trial_id==trial_id,TrialOrder.status.in_(OCCUPIED)))
def summary(db,trial):
    row=serialize(trial)
    row['occupied']=occupancy(db,trial.id)
    row['alive']=db.scalar(select(func.count()).select_from(TrialProcess).where(TrialProcess.trial_id==trial.id,TrialProcess.status=='alive'))
    return row
def listing(db):return[summary(db,t)for t in db.scalars(select(Trial).order_by(Trial.id.desc())).all()]
def detail(db,id):
    trial=get(db,id);row=summary(db,trial)
    procs={p.id:p for p in db.scalars(select(Process)).all()}
    row['processes']=[{**serialize(tp),'code':procs[tp.process_id].code,'name':procs[tp.process_id].name}for tp in db.scalars(select(TrialProcess).where(TrialProcess.trial_id==id).order_by(TrialProcess.id)).all()]
    row['stages']=[serialize(s)for s in db.scalars(select(TrialStage).where(TrialStage.trial_id==id).order_by(TrialStage.stage_no)).all()]
    orders=[]
    for o in db.scalars(select(TrialOrder).where(TrialOrder.trial_id==id).order_by(TrialOrder.id)).all():
        item={**serialize(o),'process_code':procs[o.process_id].code,'force':None,'flagged':False}
        if o.sample_id:
            sample=db.get(Sample,o.sample_id);item['force']=sample.force;item['flagged']=sample.flagged
        orders.append(item)
    row['orders']=orders
    latest=row['stages'][-1]
    row['z_bound']=latest['z_bound'];row['test_alpha']=latest['test_alpha']
    return row
def _issue_orders(db,trial,stage_no,process_ids):
    """派发一个阶段的测量单；占用试条预算，超预算即拒绝（由调用方事务保证原子性）。"""
    needed=trial.stage_size*len(process_ids)
    if occupancy(db,trial.id)+needed>trial.budget:raise HTTPException(409,'试条预算不足，无法派发下一阶段测量单')
    procs={p.id:p for p in db.scalars(select(Process).where(Process.id.in_(process_ids)))}
    for pid in process_ids:
        for i in range(1,trial.stage_size+1):
            db.add(TrialOrder(code=f'T{trial.id:03d}-S{stage_no}-{procs[pid].code}-{i:02d}',trial_id=trial.id,stage_no=stage_no,process_id=pid))
    db.flush()
def create(db,data,actor):
    if len(data.process_ids)!=len(set(data.process_ids)):raise HTTPException(422,'不能重复选择同一工艺')
    procs=[]
    for pid in data.process_ids:
        process=db.get(Process,pid)
        if not process:raise HTTPException(404,'工艺方案不存在')
        procs.append(process)
    max_stages=data.budget//(data.stage_size*len(procs))
    if max_stages<1:raise HTTPException(422,f'试条预算不足以安排一个完整阶段（每阶段需 {data.stage_size*len(procs)} 条）')
    bound,test_alpha=sequential.boundary(data.alpha,len(procs),max_stages)
    trial=Trial(title=data.title,lot=data.lot,stage_size=data.stage_size,budget=data.budget,alpha=data.alpha,max_stages=max_stages,current_stage=1,status='active',created_at=now())
    db.add(trial);db.flush()
    for p in procs:db.add(TrialProcess(trial_id=trial.id,process_id=p.id))
    db.add(TrialStage(trial_id=trial.id,stage_no=1,status='open',z_bound=bound,test_alpha=test_alpha));db.flush()
    _issue_orders(db,trial,1,[p.id for p in procs])
    db.commit()
    return detail(db,trial.id)
def claim(db,order_id,actor):
    """领单：条件更新保证并发只一人成功；已领试条不可撤回。同人重复领取幂等返回。"""
    res=db.execute(update(TrialOrder).where(TrialOrder.id==order_id,TrialOrder.status=='issued').values(status='claimed',claimed_by=actor,claimed_at=now()))
    if res.rowcount!=1:
        db.rollback();order=db.get(TrialOrder,order_id)
        if not order:raise HTTPException(404,'测量单不存在')
        if order.status=='claimed'and order.claimed_by==actor:return order
        raise HTTPException(409,'测量单已被领取、回数或撤销')
    db.commit();return db.get(TrialOrder,order_id)
def _await_reported(db,order_id,deadline=3.0):
    """并发回数冲突后等待既有回数生效，保证重试不重复入样。"""
    until=time.time()+deadline
    while time.time()<until:
        db.expire_all();order=db.get(TrialOrder,order_id)
        if order and order.status=='reported':return order
        time.sleep(0.05)
    raise HTTPException(409,'回数冲突，请刷新后重试')
def report(db,order_id,data,actor):
    """回数：生成样本并与测量单关联。已回数直接返回；样本编号唯一约束兜住并发重复。"""
    order=db.get(TrialOrder,order_id)
    if not order:raise HTTPException(404,'测量单不存在')
    if order.status=='reported':return order
    if order.status!='claimed':raise HTTPException(409,'测量单未领取或已撤销，不能回数')
    trial=get(db,order.trial_id)
    sample=Sample(code=order.code,process_id=order.process_id,lot=trial.lot,force=data.force,flagged=data.flagged,note=data.note or f'淘汰试验#{trial.id} 第{order.stage_no}阶段测量单回数')
    db.add(sample)
    try:db.flush()
    except IntegrityError:
        db.rollback();return _await_reported(db,order_id)
    res=db.execute(update(TrialOrder).where(TrialOrder.id==order_id,TrialOrder.status=='claimed').values(status='reported',sample_id=sample.id,reported_at=now()))
    if res.rowcount!=1:
        db.rollback();return _await_reported(db,order_id)
    db.commit();return db.get(TrialOrder,order_id)
def seal(db,trial_id,stage_no,actor):
    """封存阶段：按累计回数判定淘汰，撤销被淘汰工艺的未领单，同事务派发下一阶段。
    已封阶段重复调用幂等返回；半途失败整体回滚，重试不重复派单。"""
    trial=db.get(Trial,trial_id,with_for_update=True)
    if not trial:raise HTTPException(404,'淘汰试验不存在')
    stage=db.scalar(select(TrialStage).where(TrialStage.trial_id==trial_id,TrialStage.stage_no==stage_no))
    if not stage:raise HTTPException(404,'试验阶段不存在')
    if stage.status=='sealed':return detail(db,trial_id)
    if stage_no!=trial.current_stage or trial.status!='active':raise HTTPException(409,'只能封存进行中试验的当前阶段')
    alive=db.scalars(select(TrialProcess).where(TrialProcess.trial_id==trial_id,TrialProcess.status=='alive').order_by(TrialProcess.id)).all()
    procs={p.id:p for p in db.scalars(select(Process).where(Process.id.in_([a.process_id for a in alive])))}
    forces={a.process_id:[]for a in alive}
    for pid,force in db.execute(select(TrialOrder.process_id,Sample.force).join(Sample,Sample.id==TrialOrder.sample_id).where(TrialOrder.trial_id==trial_id,TrialOrder.status=='reported')).all():
        if pid in forces:forces[pid].append(force)
    groups=[{'process_id':a.process_id,'code':procs[a.process_id].code,**sequential.summarize(forces[a.process_id])}for a in alive]
    decisions,eliminated=sequential.decide(groups,stage.z_bound)
    for a in alive:
        if a.process_id in eliminated:
            a.status='eliminated';a.eliminated_stage=stage.stage_no
            a.rationale=f"第{stage.stage_no}阶段：{next(d['reason']for d in decisions if d['process_id']==a.process_id)}"
    if eliminated:
        db.execute(update(TrialOrder).where(TrialOrder.trial_id==trial_id,TrialOrder.status=='issued',TrialOrder.process_id.in_(eliminated)).values(status='revoked'))
    stage.status='sealed';stage.sealed_at=now()
    stage.decisions={'bound':stage.z_bound,'test_alpha':stage.test_alpha,'sealed_by':actor,'items':decisions}
    survivors=[a for a in alive if a.process_id not in eliminated]
    if len(survivors)<=1:
        trial.status='completed';trial.finish_reason='仅剩一个存活工艺，试验提前结束'
    elif trial.current_stage>=trial.max_stages:
        trial.status='completed';trial.finish_reason=f'已达预设最大阶段数 {trial.max_stages}，试验结束'
    elif occupancy(db,trial_id)+trial.stage_size*len(survivors)>trial.budget:
        trial.status='completed';trial.finish_reason='剩余试条预算不足以排满下一阶段，试验结束'
    else:
        trial.current_stage+=1
        db.add(TrialStage(trial_id=trial_id,stage_no=trial.current_stage,status='open',z_bound=stage.z_bound,test_alpha=stage.test_alpha));db.flush()
        _issue_orders(db,trial,trial.current_stage,[a.process_id for a in survivors])
    db.commit()
    return detail(db,trial_id)
