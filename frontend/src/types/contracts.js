/** @typedef {{id:number,code:string,name:string,temperature:number,dwell:number,pressure:number,note:string}} Process */
/** @typedef {{id:number,code:string,process_id:number,lot:string,force:number,flagged:boolean,note:string}} Sample */
/** @typedef {{id:number,title:string,status:'queued'|'running'|'completed'|'failed',snapshot:object,result:object|null,recommendation:string,approved:boolean}} Assessment */
/** @typedef {{id:number,title:string,lot:string,stage_size:number,budget:number,alpha:number,max_stages:number,current_stage:number,status:'active'|'completed',finish_reason:string,occupied:number,alive:number}} TrialSummary */
/** @typedef {{id:number,code:string,trial_id:number,stage_no:number,process_id:number,process_code:string,status:'issued'|'claimed'|'reported'|'revoked',claimed_by:string,force:number|null,sample_id:number|null}} TrialOrder */
/** @typedef {TrialSummary & {processes:Array<object>,stages:Array<object>,orders:Array<TrialOrder>,z_bound:number,test_alpha:number}} TrialDetail */
export const contractsVersion='seal-variance-2';
