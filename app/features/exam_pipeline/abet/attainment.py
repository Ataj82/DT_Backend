"""Deterministic ABET attainment aggregation."""
from __future__ import annotations
from collections import defaultdict
from typing import Any

def weighted(values):
    pairs=[(float(v), float(w)) for v,w in values if float(w)>0]
    if not pairs: return 0.0
    return sum(v*w for v,w in pairs)/sum(w for _,w in pairs)

def build_attainment(plan, session):
    turns = list(getattr(session, "turns", ()) or ())
    criterion_map = {c.id:c for c in plan.criteria}
    lo_map = {x.id:x for x in plan.learning_outcomes}
    outcome_map = {x.id:x for x in plan.outcomes}
    evidence_by_criterion=defaultdict(list)
    trace=[]
    for turn in turns:
        meta=getattr(turn,"metadata",{}) or {}
        target=(meta.get("abet") or {}).get("target") or {}
        cid=target.get("criterion_id")
        if not cid or cid not in criterion_map or not getattr(turn,"answered",False): continue
        a=(meta.get("assessment") or {})
        score=a.get("achievement_level")
        if score is None: continue
        rubric_max=6
        for r in plan.rubrics:
            if r.id==criterion_map[cid].rubric_id: rubric_max=max(1,len(r.levels))
        score=min(int(score), rubric_max)
        ev={"turn_index":turn.index,"criterion_id":cid,"score":score,"confidence":float(a.get("confidence") or 0),"evidence_strength":float(a.get("evidence_strength") or 0),"demonstrated":bool(a.get("indicator_demonstrated",a.get("demonstrated",False))),"evidence_text":a.get("feedback","") or "","missing_elements":list(a.get("missing_elements") or []),"rationale":a.get("rationale","") or ""}
        evidence_by_criterion[cid].append(ev)
        trace.append({"turn_index":turn.index,"goal_id":turn.goal_id,"indicator_id":turn.indicator_id,"criterion_id":cid,"question":turn.question,"answer":turn.answer,"score":score})
    criterion_att={}
    for cid,c in criterion_map.items():
        evs=evidence_by_criterion.get(cid,[])
        if not evs:
            criterion_att[cid]={"attainment":0.0,"coverage":0.0,"status":"unassessed","evidence":[]}
            continue
        best=max(evs,key=lambda e:(e["score"],e["evidence_strength"],e["confidence"],e["turn_index"]))
        max_level=6
        for r in plan.rubrics:
            if r.id==c.rubric_id: max_level=len(r.levels)
        att=best["score"]/max_level
        criterion_att[cid]={"attainment":att,"coverage":1.0,"status":"met" if best["score"]>=c.minimum_level else "not_met","evidence":evs}
    indicators=defaultdict(list)
    for c in plan.criteria:
        # Criteria are associated to an indicator through target metadata in turns.
        ids={t.get("indicator_id") for t in trace if t.get("criterion_id")==c.id and t.get("indicator_id")}
        for iid in ids: indicators[iid].append(c.id)
    # Include indicators present in goal model even if no evidence yet.
    for g in getattr(getattr(session,"goal_model",None),"goals",[]) or []:
        for i in getattr(g,"indicators",[]) or []: indicators.setdefault(i.id,[])
    indicator_att={}
    for iid,cids in indicators.items():
        vals=[(criterion_att[c]["attainment"],criterion_map[c].weight) for c in cids]
        cov=sum(1 for c in cids if criterion_att[c]["coverage"]>0)/len(cids) if cids else 0.0
        att=weighted(vals)
        indicator_att[iid]={"attainment":att,"coverage":cov,"status":"passed" if cids and cov>=plan.required_coverage and att>=plan.minimum_attainment else ("insufficient_evidence" if cov<plan.required_coverage else "in_progress"),"criteria":{c:criterion_att[c] for c in cids}}
    goal_att={}
    for lo in plan.learning_outcomes:
        vals=[]
        goal_ids=set(lo.goal_ids)
        for gid in goal_ids:
            cids=[c.id for c in plan.criteria if (c.goal_id==gid or (c.goal_id is None and c.learning_outcome_id==lo.id)) and (c.learning_outcome_id in (None,lo.id))]
            vals.extend((criterion_att[c]["attainment"], criterion_map[c].weight) for c in cids)
        cov=(sum(1 for c in plan.criteria if c.learning_outcome_id==lo.id and criterion_att[c.id]["coverage"]>0)/sum(1 for c in plan.criteria if c.learning_outcome_id==lo.id)) if any(c.learning_outcome_id==lo.id for c in plan.criteria) else 0.0
        att=weighted(vals)
        goal_att[lo.id]={"attainment":att,"coverage":cov,"status":"passed" if vals and cov>=plan.required_coverage and att>=lo.passing_threshold else ("insufficient_evidence" if cov<plan.required_coverage else "in_progress")}
    outcomes={}
    for o in plan.outcomes:
        vals=[(goal_att[x]["attainment"],lo_map[x].weight) for x in o.learning_outcome_ids if x in goal_att]
        coverage = (sum(1 for x in o.learning_outcome_ids if x in goal_att and goal_att[x]["coverage"] >= plan.required_coverage) / len(vals)) if vals else 0.0
        outcome_attainment=weighted(vals)
        outcomes[o.id]={"code":o.code,"title":o.title,"attainment":outcome_attainment,"coverage":coverage,"status":"passed" if vals and coverage>=plan.required_coverage and outcome_attainment>=o.passing_threshold else ("insufficient_evidence" if coverage<plan.required_coverage else "in_progress")}
    return {"plan_id":plan.id,"criteria":criterion_att,"indicators":indicator_att,"learning_outcomes":goal_att,"outcomes":outcomes,"traceability":trace,"completed":bool(outcomes) and all(x["status"]=="passed" for x in outcomes.values())}
