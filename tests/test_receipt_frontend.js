// Run with Node.js; no dependencies, browser, network, credentials or payments.
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const code=fs.readFileSync(require('node:path').join(__dirname, '../static/js/receipt.js'),'utf8');
const KEY='zeuz_checkout_attempt_v1';
const initial=[{id:'zeuzdnc-touch',qty:1}];
const cartKey=items=>JSON.stringify(items.map(item=>({id:item.id,qty:item.qty})).sort((a,b)=>a.id.localeCompare(b.id)));
function run({receipt={id:'order-1',paid:true},attempt={id:'attempt-1',orderId:'order-1',cartKey:cartKey(initial)},cart=structuredClone(initial),getBlocked=false,removeBlocked=false}={}) {
 const storage=new Map();if(attempt!==null)storage.set(KEY,typeof attempt==='string'?attempt:JSON.stringify(attempt));
 const state={clears:0,cart};
 const Cart={get:()=>state.cart,clear(){state.clears++;state.cart=[];}};
 const StoreQuote={cartKey};const element=receipt===null?null:{textContent:typeof receipt==='string'?receipt:JSON.stringify(receipt)};
 const context={window:{Cart,StoreQuote},Cart,StoreQuote,document:{getElementById:()=>element},sessionStorage:{getItem(k){if(getBlocked)throw Error('blocked');return storage.get(k)||null;},removeItem(k){if(removeBlocked)throw Error('blocked');storage.delete(k);}}};
 vm.createContext(context);const execute=()=>vm.runInContext(code,context);execute();return {state,storage,execute};
}
let r=run();assert.equal(r.state.clears,1);assert.ok(!r.storage.has(KEY));
r.state.cart=structuredClone(initial);r.execute();assert.equal(r.state.clears,1);assert.equal(r.state.cart.length,1); // repeated old receipt preserves a new selection
r=run({cart:[{id:'zeuzdnc-touch',qty:2}]});assert.equal(r.state.clears,0);assert.ok(!r.storage.has(KEY));
r=run({attempt:{orderId:'newer-order',cartKey:cartKey(initial)}});assert.equal(r.state.clears,0);assert.ok(r.storage.has(KEY));
r=run({receipt:{id:'order-1',paid:false}});assert.equal(r.state.clears,0);assert.ok(r.storage.has(KEY));
r=run({receipt:null});assert.equal(r.state.clears,0);assert.ok(r.storage.has(KEY));
r=run({attempt:null});assert.equal(r.state.clears,0);
r=run({receipt:'bad JSON'});assert.equal(r.state.clears,0);assert.ok(r.storage.has(KEY));
r=run({attempt:'bad JSON'});assert.equal(r.state.clears,0);assert.ok(r.storage.has(KEY));
r=run({getBlocked:true});assert.equal(r.state.clears,0);assert.ok(r.storage.has(KEY));
r=run({removeBlocked:true});assert.equal(r.state.clears,0);assert.ok(r.storage.has(KEY));
r=run({attempt:{orderId:'order-1'}});assert.equal(r.state.clears,0);assert.ok(!r.storage.has(KEY));
console.log('PASS: 12 receipt scenarios — paid/matching clears once; changed cart, stale receipt, unknown/unpaid, absent or corrupt storage and blocked storage preserve cart.');
