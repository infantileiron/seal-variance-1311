import threading
import pytest
from fastapi.testclient import TestClient

@pytest.fixture(scope='session')
def client():
    from src.main import app
    from scripts.seed_demo import seed
    with TestClient(app) as c:
        seed()
        yield c

def auth(client,email):
    r=client.post('/auth/login',json={'email':email,'password':'Demo123!'})
    assert r.status_code==200,r.text
    return{'Authorization':'Bearer '+r.json()['access_token']}

@pytest.fixture(scope='session')
def analyst(client):return auth(client,'analyst@demo.local')
@pytest.fixture(scope='session')
def viewer(client):return auth(client,'viewer@demo.local')

def make_trial(client,h,title,stage_size=2,budget=8,alpha=0.05,process_ids=(1,2)):
    r=client.post('/trials',json={'title':title,'lot':'HC-1115','stage_size':stage_size,'budget':budget,'alpha':alpha,'process_ids':list(process_ids)},headers=h)
    assert r.status_code==201,r.text
    return r.json()

def detail(client,h,tid):return client.get(f'/trials/{tid}',headers=h).json()

def claim_report(client,h,order,force):
    assert client.post(f"/orders/{order['id']}/claim",headers=h).status_code==200
    r=client.post(f"/orders/{order['id']}/report",json={'force':force},headers=h)
    assert r.status_code==200,r.text

def test_create_issues_first_stage_and_fixed_bound(client,analyst):
    t=make_trial(client,analyst,'T 创建与边界')
    assert t['status']=='active'and t['current_stage']==1 and t['max_stages']==2
    assert t['occupied']==4 and len(t['orders'])==4 and all(o['status']=='issued' for o in t['orders'])
    assert t['stages'][0]['test_alpha']==pytest.approx(0.025)
    assert t['stages'][0]['z_bound']==pytest.approx(1.959964,abs=1e-5)
    assert t['z_bound']==t['stages'][0]['z_bound']

def test_create_validation(client,analyst,viewer):
    h={'content-type':'application/json',**analyst}
    assert client.post('/trials',json={'title':'T 创建与边界','lot':'L','stage_size':2,'budget':8,'alpha':0.05,'process_ids':[1,2]},headers=analyst).status_code==409
    assert client.post('/trials',json={'title':'T 预算不足','lot':'L','stage_size':2,'budget':3,'alpha':0.05,'process_ids':[1,2]},headers=analyst).status_code==422
    assert client.post('/trials',json={'title':'T 重复工艺','lot':'L','stage_size':2,'budget':8,'alpha':0.05,'process_ids':[1,1]},headers=analyst).status_code==422
    assert client.post('/trials',json={'title':'T 工艺缺失','lot':'L','stage_size':2,'budget':8,'alpha':0.05,'process_ids':[1,999]},headers=analyst).status_code==404
    assert client.post('/trials',json={'title':'T 只读','lot':'L','stage_size':2,'budget':8,'alpha':0.05,'process_ids':[1,2]},headers=viewer).status_code==403

def test_early_elimination_and_late_report(client,analyst):
    t=make_trial(client,analyst,'T 早淘汰',stage_size=4,budget=16)
    d=detail(client,analyst,t['id'])
    low=[o for o in d['orders'] if o['process_code']=='HC-S1']
    high=[o for o in d['orders'] if o['process_code']=='HC-S2']
    for o,v in zip(low,[20.0,20.1,19.9]):claim_report(client,analyst,o,v)  # 第4张未领，淘汰后应被撤销
    for o,v in zip(high[:3],[30.0,30.1,29.9]):claim_report(client,analyst,o,v)
    assert client.post(f"/orders/{high[3]['id']}/claim",headers=analyst).status_code==200  # 已领未测：封存后迟回数
    r=client.post(f"/trials/{t['id']}/stages/1/seal",headers=analyst)
    assert r.status_code==200,r.text
    d=r.json()
    assert d['status']=='completed'and'仅剩一个存活工艺' in d['finish_reason']
    assert all(o['stage_no']==1 for o in d['orders'])  # 未再派单，预算未继续消耗
    s1=next(p for p in d['processes'] if p['code']=='HC-S1')
    assert s1['status']=='eliminated'and s1['eliminated_stage']==1 and'判定淘汰' in s1['rationale']
    items=d['stages'][0]['decisions']['items']
    lead=next(i for i in items if i['conclusion']=='lead');out=next(i for i in items if i['conclusion']=='eliminated')
    assert lead['code']=='HC-S2'and out['code']=='HC-S1'and out['z']>d['stages'][0]['z_bound']
    revoked=[o for o in d['orders'] if o['status']=='revoked']
    assert len(revoked)==1 and revoked[0]['process_code']=='HC-S1'  # 未领单撤销，释放预算
    before=d['stages'][0]['decisions']
    late=client.post(f"/orders/{high[3]['id']}/report",json={'force':30.2},headers=analyst)  # 迟回数
    assert late.status_code==200 and late.json()['status']=='reported'
    again=detail(client,analyst,t['id'])
    assert again['stages'][0]['decisions']==before  # 已封阶段判定不被迟回数改写
    assert next(o for o in again['orders'] if o['id']==high[3]['id'])['force']==30.2
    codes=[s['code'] for s in client.get('/samples',headers=analyst).json()]
    assert codes.count(high[3]['code'])==1  # 回数入库并关联原样本，全库唯一样本
    r=client.post(f"/trials/{t['id']}/stages/1/seal",headers=analyst)  # 已封阶段重复封存幂等
    assert r.status_code==200 and r.json()['orders']==again['orders']

def test_insufficient_evidence_kept_and_stage_rolls_on(client,analyst):
    t=make_trial(client,analyst,'T 证据不足')
    r=client.post(f"/trials/{t['id']}/stages/1/seal",headers=analyst)
    assert r.status_code==200,r.text
    d=r.json()
    assert d['status']=='active'and d['current_stage']==2
    items=d['stages'][0]['decisions']['items']
    assert all(i['conclusion']=='kept'and'证据不足' in i['reason'] for i in items)
    assert len([o for o in d['orders'] if o['stage_no']==2])==4  # 下一阶段照常派单
    assert d['occupied']==8<=d['budget']
    r=client.post(f"/trials/{t['id']}/stages/2/seal",headers=analyst)  # 达到最大阶段数
    assert r.status_code==200 and r.json()['status']=='completed'and'最大阶段数' in r.json()['finish_reason']

def test_seal_failure_rolls_back_and_retry_is_clean(client,analyst,monkeypatch):
    t=make_trial(client,analyst,'T 封存半途失败')
    d=detail(client,analyst,t['id'])
    forces={'HC-S1':[30.0,30.2],'HC-S2':[30.1,30.3]}
    for o in d['orders']:claim_report(client,analyst,o,forces[o['process_code']].pop(0))
    import src.services.trials as svc
    def boom(db,trial,stage_no,pids):raise RuntimeError('injected failure')
    monkeypatch.setattr(svc,'_issue_orders',boom)
    r=client.post(f"/trials/{t['id']}/stages/1/seal",headers=analyst)
    assert r.status_code==500
    monkeypatch.undo()
    d=detail(client,analyst,t['id'])  # 半途失败整体回滚：阶段仍开、无判定、无新单、无淘汰
    assert d['status']=='active'and d['current_stage']==1
    assert d['stages'][0]['status']=='open'and d['stages'][0]['decisions'] is None
    assert len(d['orders'])==4 and all(p['status']=='alive' for p in d['processes'])
    r=client.post(f"/trials/{t['id']}/stages/1/seal",headers=analyst)  # 重试成功且不重复派单
    assert r.status_code==200,r.text
    d=r.json()
    assert d['stages'][0]['status']=='sealed'and d['current_stage']==2
    assert len(d['orders'])==8 and len([o for o in d['orders'] if o['stage_no']==2])==4
    r=client.post(f"/trials/{t['id']}/stages/1/seal",headers=analyst)  # 重复封存已封阶段：幂等，不重复派单
    assert r.status_code==200 and len(r.json()['orders'])==8

def test_concurrent_claim_and_report(client,analyst):
    from src.config.database import SessionLocal
    from src.services import trials as svc
    t=make_trial(client,analyst,'T 并发领单回数')
    oid=detail(client,analyst,t['id'])['orders'][0]['id']
    results=[]
    def claim_worker(i):
        from fastapi import HTTPException
        with SessionLocal() as db:
            try:svc.claim(db,oid,f'user{i}@demo.local');results.append('ok')
            except HTTPException:results.append('conflict')
    threads=[threading.Thread(target=claim_worker,args=(i,))for i in range(8)]
    [x.start()for x in threads];[x.join()for x in threads]
    assert results.count('ok')==1 and results.count('conflict')==7  # 并发领单只有一人成功
    winner=detail(client,analyst,t['id'])['orders'][0]['claimed_by']
    reports=[]
    def report_worker(i):
        from fastapi import HTTPException
        from src.schemas.business import ReportInput
        with SessionLocal() as db:
            try:svc.report(db,oid,ReportInput(force=25.0+i),winner);reports.append('ok')
            except HTTPException:reports.append('conflict')
    threads=[threading.Thread(target=report_worker,args=(i,))for i in range(8)]
    [x.start()for x in threads];[x.join()for x in threads]
    assert reports.count('ok')==8  # 并发回数幂等收敛，不报错也不重复入样
    o=next(o for o in detail(client,analyst,t['id'])['orders'] if o['id']==oid)
    assert o['status']=='reported'
    codes=[s['code'] for s in client.get('/samples',headers=analyst).json()]
    assert codes.count(o['code'])==1

def test_viewer_readonly_and_assessments_intact(client,viewer,analyst):
    t=make_trial(client,analyst,'T 权限')
    oid=t['orders'][0]['id']
    assert client.get('/trials',headers=viewer).status_code==200
    assert client.get(f"/trials/{t['id']}",headers=viewer).status_code==200
    assert client.post(f"/orders/{oid}/claim",headers=viewer).status_code==403
    assert client.post(f"/orders/{oid}/report",json={'force':25.0},headers=viewer).status_code==403
    assert client.post(f"/trials/{t['id']}/stages/1/seal",headers=viewer).status_code==403
    assert client.get('/assessments',headers=viewer).status_code==200  # 原方差评议照常可用
