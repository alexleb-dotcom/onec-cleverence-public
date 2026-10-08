/**
 * Q108 durable HTTPS Pull state machine, reused from the PR #58 spike.
 * All state transitions require store.tx() to atomically commit the mailbox
 * together with the real S4 accounting adapter's mutations and receipt hashes.
 * The production adapter, authentication and routes live in src/https-pull.mjs.
 */
const MAX_ARGS_BYTES = 4096;
const MAX_RESULT_BYTES = 3000;
const encoder = new TextEncoder();
const bytes = value => encoder.encode(JSON.stringify(value)).byteLength;
const owns = (job, id) => job.admission === id.admission && job.session === id.session && job.snapshot === id.snapshot;
const isActive = (task, id, now) => task?.admission === id.admission && task.session === id.session && task.snapshot === id.snapshot && now < task.expires;
const copy = value => structuredClone(value);

export class PullMailbox {
  constructor({store, accounting, now = () => Date.now(), newToken = () => crypto.randomUUID(), maxArgsBytes = MAX_ARGS_BYTES}) {
    this.store = store;
    this.accounting = accounting;
    this.now = now;
    this.newToken = newToken;
    this.maxArgsBytes = maxArgsBytes;
  }
  /** The task binding is pinned, as with the already-admitted S4 task. */
  async enqueue({requestId, fingerprint, identity, op, args, deadline}) {
    const t = this.now();
    if (!/^mcp-[0-9a-f]{64}$/.test(requestId) || !/^[a-z_]{1,32}$/.test(op) ||
        typeof fingerprint !== 'string' || bytes(args) > this.maxArgsBytes ||
        !Number.isSafeInteger(deadline) || deadline <= t || deadline > t + 15000)
      return {status:'INVALID'};
    return this.store.tx(async data => {
      const current=this.now();
      await this.expireData(data, current);
      if (!isActive(data.task, identity, current)) return {status:'TASK_NOT_ACTIVE'};
      let job = data.job;
      if (job?.requestId === requestId) {
        if (job.fingerprint !== fingerprint || !owns(job, identity)) return {status:'ID_COLLISION'};
        if (job.status !== 'EXPIRED_UNCLAIMED') return {status:job.status, replay:true};
      }
      if (job && (job.status === 'PENDING' || job.status === 'LEASED')) return {status:'BUSY'};
      const replay=await this.accounting.lookup?.(data.s4,{requestId,fingerprint,op,args});
      if(replay)return replay;
      // Old terminal results remain in bounded receipts; never re-use their IDs.
      if (data.receipts[requestId] && data.receipts[requestId].status !== 'EXPIRED_UNCLAIMED') return {status:'ALREADY_ACCOUNTED'};
      const proposal = {requestId, fingerprint, admission:identity.admission, session:identity.session,
        snapshot:identity.snapshot, op, args:copy(args), deadline, status:'PENDING', created:t};
      data.job = proposal;
      return {status:'PENDING', replay:false}; // no S4 mutation
    });
  }
  /** Private authenticated outbound-helper polling endpoint owner. */
  async claim({identity, helperId}) {
    const token = this.newToken();
    return this.store.tx(async data => {
      const t=this.now();
      await this.expireData(data, t);
      if (!isActive(data.task, identity, t)) return {status:'TASK_NOT_ACTIVE'};
      const job = data.job;
      if (!job || !owns(job, identity)) return {status:'EMPTY'};
      if (job.status === 'LEASED') {
        if (job.helperId !== helperId) return {status:'BUSY'};
        if (t >= job.deadline) return {status:'EXPIRED_RESERVED'};
        return {status:'CLAIMED', replay:true, requestId:job.requestId, token:job.token,
          op:job.op, args:copy(job.args), deadline:job.deadline};
      }
      if (job.status !== 'PENDING') return {status:'EMPTY'};
      if (t >= job.deadline) { job.status='EXPIRED_UNCLAIMED';data.receipts[job.requestId]={status:job.status};return {status:'EMPTY'}; }
      // The actual S4 reserve and lease commit in the SAME durable transaction.
      const reservation = await this.accounting.reserve(data.s4, job, data);
      if (reservation && reservation.action !== 'EXECUTE') {
        job.status='BLOCKED';job.blocked=reservation;job.args=null;
        return {status:'EMPTY'};
      }
      job.status='LEASED';job.helperId=helperId;job.token=token;job.claimed=t;
      return {status:'CLAIMED', replay:false, requestId:job.requestId, token:job.token,
        op:job.op, args:copy(job.args), deadline:job.deadline};
    });
  }
  /** A result accepted once under the exact active lease, even across wakeups. */
  async complete({identity, helperId, requestId, token, result}) {
    if (!result || !['OK','ERROR'].includes(result.status) || bytes(result.payload) > MAX_RESULT_BYTES)
      return {status:'RESULT_INVALID'};
    return this.store.tx(async data => {
      const t=this.now();
      await this.expireData(data, t);
      const job = data.job;
      if (!job || !owns(job, identity) || job.requestId !== requestId ||
          job.helperId !== helperId || job.token !== token) return {status:'LEASE_REJECTED'};
      if (job.status === 'COMMITTED') {
        return JSON.stringify(job.result) === JSON.stringify(result) ? {status:'COMMITTED', replay:true} : {status:'RESULT_CONFLICT'};
      }
      if (job.status !== 'LEASED' || t >= job.deadline) return {status:'EXPIRED_RESERVED'};
      const committed = await this.accounting.commit(data.s4, job, result, data);
      job.status=committed?.error ? 'AMBIGUOUS_CHARGED' : 'COMMITTED';job.result=copy(result);job.response=committed;job.args=null;
      this.remember(data, requestId, {status:job.status});
      return {status:'COMMITTED',replay:false};
    });
  }
  /** Invoked after an RPC waiter times out, and on next poll or DO wake. */
  async expire() {
    return this.store.tx(data => this.expireData(data,this.now()));
  }
  remember(data, id, receipt) {
    data.receipts[id]=receipt;
    while(Object.keys(data.receipts).length>8)delete data.receipts[Object.keys(data.receipts)[0]];
  }
  async expireData(data,t) {
      const j=data.job;
      if (!j || t<j.deadline) return {status:'NO_CHANGE'};
      if (j.status==='PENDING') {
        j.status='EXPIRED_UNCLAIMED';j.args=null;
        this.remember(data,j.requestId,{status:'EXPIRED_UNCLAIMED'});
        return {status:j.status,charged:false};
      }
      if (j.status==='LEASED') {
        await this.accounting.ambiguous(data.s4,j);
        j.status='AMBIGUOUS_CHARGED';j.args=null;
        this.remember(data,j.requestId,{status:j.status});
        return {status:j.status,charged:true};
      }
      return {status:j.status,charged:false};
  }
  async status({identity,requestId}) {
    return this.store.tx(async data => {
      await this.expireData(data,this.now());
      const j=data.job;
      if (!j || j.requestId!==requestId || !owns(j,identity)) return {status:'NOT_FOUND'};
      if (j.status==='COMMITTED') return {status:j.status,result:copy(j.result),response:copy(j.response)};
      if (j.status==='BLOCKED') return {status:j.status,blocked:copy(j.blocked)};
      if (j.status==='AMBIGUOUS_CHARGED') return {status:j.status,response:copy(j.response)};
      return {status:j.status};
    });
  }
}
