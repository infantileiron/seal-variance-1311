import math
from scipy.stats import norm

def boundary(alpha,n_processes,max_stages):
    """Bonferroni 拆分：整场至多 (G-1)*K 次淘汰检验，每次检验 α' = α/((G-1)*K)。
    边界在创建时固定，任意次查看数据不改变边界，整场误淘汰概率 ≤ α。"""
    test_alpha=alpha/((n_processes-1)*max_stages)
    return float(norm.ppf(1-test_alpha)),test_alpha

def summarize(forces):
    n=len(forces)
    if not n:return{'n':0,'mean':None,'sd':None}
    mean=sum(forces)/n
    sd=math.sqrt(sum((f-mean)**2 for f in forces)/(n-1)) if n>1 else None
    return{'n':n,'mean':mean,'sd':sd}

def welch_z(lead,g):
    se2=lead['sd']**2/lead['n']+g['sd']**2/g['n']
    diff=lead['mean']-g['mean']
    if se2<=1e-12:return math.inf if diff>0 else 0.0
    return diff/math.sqrt(se2)

def decide(groups,bound):
    """以累计均值最高者为对照，对其余存活工艺作单侧 Welch z 检验。
    返回 (判定依据列表, 淘汰工艺 id 列表)；证据不足一律保留并写明原因。"""
    valid=[g for g in groups if g['n']>=1]
    lead=max(valid,key=lambda g:(g['mean'],-g['process_id'])) if valid else None
    decisions=[];eliminated=[]
    for g in groups:
        d={'process_id':g['process_id'],'code':g['code'],'n':g['n'],'mean':round(g['mean'],4) if g['mean'] is not None else None,'sd':round(g['sd'],4) if g['sd'] is not None else None,'z':None}
        if lead and g['process_id']==lead['process_id']:
            d.update(conclusion='lead',reason=f"累计均值 {lead['mean']:.2f}N 为存活工艺最高，作为本阶段对照基准")
        elif g['n']<2:
            d.update(conclusion='kept',reason=f"有效回数 {g['n']} 条，不足 2 条无法估计组内变异，证据不足保留续测")
        elif lead['n']<2:
            d.update(conclusion='kept',reason='领先工艺有效回数不足 2 条，无法构造检验，证据不足保留续测')
        else:
            z=welch_z(lead,g)
            if math.isinf(z):
                d.update(conclusion='eliminated',reason=f"两组回数均无变异且累计均值落后领先工艺（{g['mean']:.2f}N 对 {lead['mean']:.2f}N），判定淘汰")
                eliminated.append(g['process_id'])
            else:
                d['z']=round(z,4)
                if z>bound:
                    d.update(conclusion='eliminated',reason=f"累计 {g['n']} 条、均值 {g['mean']:.2f}N，落后领先工艺 z={z:.2f} 超过本阶段边界 {bound:.2f}，判定淘汰")
                    eliminated.append(g['process_id'])
                else:
                    d.update(conclusion='kept',reason=f"累计 {g['n']} 条、均值 {g['mean']:.2f}N，z={z:.2f} 未达本阶段边界 {bound:.2f}，证据不足保留续测")
        decisions.append(d)
    return decisions,eliminated
