from fastapi import APIRouter,Depends
from src.config.database import get_db
from src.utils.security import current_user,editor
from src.schemas.business import TrialInput,ReportInput
from src.services import trials
from src.controllers.business import serialize
router=APIRouter()
@router.get('/trials')
def listing(db=Depends(get_db),user=Depends(current_user)):return trials.listing(db)
@router.post('/trials',status_code=201)
def create(data:TrialInput,db=Depends(get_db),user=Depends(editor)):return trials.create(db,data,user.email)
@router.get('/trials/{id}')
def detail(id:int,db=Depends(get_db),user=Depends(current_user)):return trials.detail(db,id)
@router.post('/trials/{id}/stages/{stage_no}/seal')
def seal(id:int,stage_no:int,db=Depends(get_db),user=Depends(editor)):return trials.seal(db,id,stage_no,user.email)
@router.post('/orders/{id}/claim')
def claim(id:int,db=Depends(get_db),user=Depends(editor)):return serialize(trials.claim(db,id,user.email))
@router.post('/orders/{id}/report')
def report(id:int,data:ReportInput,db=Depends(get_db),user=Depends(editor)):return serialize(trials.report(db,id,data,user.email))
