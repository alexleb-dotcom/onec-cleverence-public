/**
 * Q108 HTTPS Pull feasibility SPIKE — NOT production S4 integration.
 * All state transitions require store.tx() to atomically commit the mailbox
 * together with the provided S4 accounting adapter's synchronous mutations.
 * An existing SQLite-backed Durable Object can supply this boundary, but
 * this module deliberately has no production routes or authentication.
 */
const MAX_ARGS_BYTES = 4096;
const MAX_RESULT_BYTES = 3000;
const encoder = new TextEncoder();
const bytes = value => encoder.encode(JSON.stringify(value)).byteLength;
const owns = (job, id) => job.admission === id.admission && job.session === id.session && job.snapshot === id.snapshot;
const isActive = (task, id, now) => task?.admission === id.admission && task.session === id.session && task.snapshot === id.snapshot && now < task.expires;
const copy = value => structuredClone(value);

export class PullMailbox {
  constructor({store, accounting, now = () => Date.now(), newToken = () => crypto.randomUUID()}) {
    this.store = store;
    this.accounting = accounting;
    this.now = now;
    this.newToken = newToken;
  }
  /** The task binding is pinned, as with the already-admitted S4 task. */
  async enqueue({requestId, fingerprint, identity, op, args, deadline}) {
    const t = this.now();
    if (!/^mcp-[0-9a-f]{64}$/.test(requestId) || !/^[a-z_]{1,32}$/.test(op) ||
        typeof fingerprint !== 'string' || bytes(args) > MAX_ARGS_BYTES ||
        !Number.isSafeInteger(deadline) || deadline <= t || deadline > t + 15000)
      return {status:'INVALID'};
    return this.store.tx(data => {
      if (!isActive(data.task, identity, t)) return {status:'TASK_NOT_ACTIVE'};
      let job = data.job;
      if (job?.requestId === requestId) {
        if (job.fingerprint !== fingerprint || !owns(job, identity)) return {status:'ID_COLLISION'};
        return {status:job.status, replay:true};
      }
      if (job && (job.status === 'PENDING' || job.status === 'LEASED')) return {status:'BUSY'};
      // Old terminal results remain in bounded receipts; never re-use their IDs.
      if (data.receipts[requestId]) return {status:'ALREADY_ACCOUNTED'};
      const proposal = {requestId, fingerprint, admission:identity.admission, session:identity.session,
        snapshot:identity.snapshot, op, args:copy(args), deadline, status:'PENDING', created:t};
      data.job = proposal;
      return {status:'PENDING', replay:false}; // no S4 mutation
    });
  }
  /** Private authenticated outbound-helper polling endpoint owner. */
  async claim({identity, helperId}) {
    const t = this.now();
    return this.store.tx(data => {
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
      // Atomicity REQUIREMENT: the actual S4 reserve must be committed in the
      // SAME durable transaction as the lease. The hook is synchronous/pure.
      this.accounting.reserve(data.s4, job);
      job.status='LEASED';job.helperId=helperId;job.token=this.newToken();job.claimed=t;
      return {status:'CLAIMED', replay:false, requestId:job.requestId, token:job.token,
        op:job.op, args:copy(job.args), deadline:job.deadline};
    });
  }
  /** A result accepted once under the exact active lease, even across wakeups. */
  async complete({identity, helperId, requestId, token, result}) {
    const t = this.now();
    if (!result || !['OK','ERROR'].includes(result.status) || bytes(result.payload) > MAX_RESULT_BYTES)
      return {status:'RESULT_INVALID'};
    return this.store.tx(data => {
      const job = data.job;
      if (!job || !owns(job, identity) || job.requestId !== requestId ||
          job.helperId !== helperId || job.token !== token) return {status:'LEASE_REJECTED'};
      if (job.status === 'COMMITTED') {
        return JSON.stringify(job.result) === JSON.stringify(result) ? {status:'COMMITTED', replay:true} : {status:'RESULT_CONFLICT'};
      }
      if (job.status !== 'LEASED' || t >= job.deadline) return {status:'EXPIRED_RESERVED'};
      this.accounting.commit(data.s4, job, result);
      job.status='COMMITTED';job.result=copy(result);job.args=null;
      data.receipts[requestId]={status:'COMMITTED', result:copy(result)};
      return {status:'COMMITTED',replay:false};
    });
  }
  /** Invoked after an RPC waiter times out, and on next poll or DO wake. */
  async expire() {
    const t=this.now();
    return this.store.tx(data => {
      const j=data.job;
      if (!j || t<j.deadline) return {status:'NO_CHANGE'};
      if (j.status==='PENDING') {
        j.status='EXPIRED_UNCLAIMED';j.args=null;
        data.receipts[j.requestId]={status:'EXPIRED_UNCLAIMED'};
        return {status:j.status,charged:false};
      }
      if (j.status==='LEASED') {
        this.accounting.ambiguous(data.s4,j);
        j.status='AMBIGUOUS_CHARGED';j.args=null;
        data.receipts[j.requestId]={status:j.status};
        return {status:j.status,charged:true};
      }
      return {status:j.status,charged:false};
    });
  }
  async status({identity,requestId}) {
    return this.store.tx(data => {
      const j=data.job;
      if (!j || j.requestId!==requestId || !owns(j,identity)) return {status:'NOT_FOUND'};
      if (j.status==='COMMITTED') return {status:j.status,result:copy(j.result)};
      return {status:j.status};
    });
  }
}
