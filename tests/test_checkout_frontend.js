// Run with Node.js; no dependencies, browser, network, credentials or payments.
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {webcrypto} = require('node:crypto');
const code = fs.readFileSync(require('node:path').join(__dirname, '../static/js/checkout.js'),'utf8');
function harness({blockedStorage=false}={}) {
 const events={}; const cartEvents=[]; const storage=new Map(); const requests=[]; const redirects=[];
 const cart=[{id:'zeuzdnc-touch',qty:1}];
 let snapshot={state:'ready',quote:{quote_token:'a'.repeat(64)},cartKey:JSON.stringify(cart)};
 let responder=async()=>({ok:true,status:200,json:async()=>({ok:true,order_id:'test-order',redirect_url:'https://checkout.stripe.com/c/pay/test_123'})});
 const button={dataset:{},disabled:true,textContent:''};const fields={disabled:false};const error={hidden:true,textContent:'',focus(){this.focused=true;}};
 const form={elements:{name:{value:' Test Buyer '},email:{value:' BUYER@example.com '},phone:{value:''}},reportValidity:()=>true,setAttribute(){},addEventListener(type,fn){events[type]=fn;}};
 const quote={get:()=>snapshot,refresh(){this.refreshes++;snapshot={state:'pending',quote:null,cartKey:JSON.stringify(cart)};},refreshes:0,cartKey(items){return JSON.stringify([...items].sort((a,b)=>a.id.localeCompare(b.id)));}};
 const win={__STORE__:{payments_enabled:true,gateways:['stripe']},crypto:webcrypto,StoreQuote:quote,addEventListener(){},location:{origin:'https://www.zeuzdnc.com',assign:u=>redirects.push(u)}};
 const context={window:win,StoreQuote:quote,crypto:webcrypto,document:{getElementById:id=>({'checkout-form':form,'submit-btn':button,'checkout-contact':fields,'form-error':error}[id])},Cart:{get:()=>structuredClone(cart),onChange:fn=>cartEvents.push(fn)},sessionStorage:{getItem(k){if(blockedStorage)throw Error('blocked');return storage.get(k)||null;},setItem(k,v){if(blockedStorage)throw Error('blocked');storage.set(k,v);},removeItem(k){storage.delete(k);}},fetch:async(url,options)=>{requests.push({url,options,body:JSON.parse(options.body)});return responder(options);},setTimeout,clearTimeout,TextEncoder,Uint8Array,DOMException,AbortController,URL,SyntaxError};
 vm.createContext(context);vm.runInContext(code,context);
 return {submit:()=>events.submit({preventDefault(){}}),button,fields,error,requests,redirects,storage,quote,cart,setResponder:fn=>{responder=fn;},ready(token='a'.repeat(64)){snapshot={state:'ready',quote:{quote_token:token},cartKey:JSON.stringify(cart)};},cartChange(){cart[0].qty++;cartEvents.forEach(fn=>fn());}};
}
async function waitFor(fn){for(let i=0;i<100;i++){if(fn())return;await new Promise(r=>setTimeout(r,2));}throw Error('wait timed out');}
(async()=>{
 let h=harness();await h.submit();assert.equal(h.requests.length,1);assert.equal(h.requests[0].body.customer.email,'buyer@example.com');assert.match(h.requests[0].body.attempt_id,/^[\da-f-]{36}$/);assert.equal(h.requests[0].body.quote_token,'a'.repeat(64));assert.equal(h.redirects.length,1);assert.ok(![...h.storage.values()].join().includes('buyer'));const saved=JSON.parse(h.storage.get('zeuz_checkout_attempt_v1'));assert.equal(saved.orderId,'test-order');assert.equal(saved.cartKey,JSON.stringify(h.cart));
 h=harness();let calls=0;h.setResponder(async()=>{if(++calls===1)throw Error('Failed to fetch');return {ok:true,json:async()=>({ok:true,order_id:'test-order',redirect_url:'https://checkout.stripe.com/c/pay/retry'})};});await h.submit();assert.ok(!h.error.hidden);await h.submit();assert.equal(h.requests[0].body.attempt_id,h.requests[1].body.attempt_id);
 h=harness({blockedStorage:true});calls=0;h.setResponder(async()=>{if(++calls===1)throw Error('Failed to fetch');return {ok:true,json:async()=>({ok:true,order_id:'test-order',redirect_url:'https://checkout.stripe.com/c/pay/retry'})};});await h.submit();await h.submit();assert.equal(h.requests[0].body.attempt_id,h.requests[1].body.attempt_id);
 h=harness();h.setResponder(async()=>({ok:false,status:409,json:async()=>({ok:false,code:'quote_changed'})}));await h.submit();assert.equal(h.quote.refreshes,1);assert.equal(h.redirects.length,0);assert.ok(h.button.disabled);const old=h.requests[0].body.attempt_id;h.ready('b'.repeat(64));h.setResponder(async()=>({ok:true,json:async()=>({ok:true,order_id:'test-order',redirect_url:'https://checkout.stripe.com/c/pay/new'})}));await h.submit();assert.notEqual(h.requests[1].body.attempt_id,old);
 h=harness();let resolve;h.setResponder(()=>new Promise(r=>resolve=r));const first=h.submit();await waitFor(()=>h.requests.length);await h.submit();assert.equal(h.requests.length,1);resolve({ok:true,json:async()=>({ok:true,order_id:'test-order',redirect_url:'https://checkout.stripe.com/c/pay/once'})});await first;assert.equal(h.redirects.length,1);
 h=harness();h.setResponder(async()=>({ok:true,json:async()=>({ok:true,order_id:'test-order',redirect_url:'https://evil.example/pay'})}));await h.submit();assert.equal(h.redirects.length,0);assert.match(h.error.textContent,/dirección de pago/);
 h=harness();h.setResponder(options=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))));const pending=h.submit();await waitFor(()=>h.requests.length);h.cartChange();await pending;assert.equal(h.redirects.length,0);assert.match(h.error.textContent,/otra pestaña/);
 h=harness();h.setResponder(async()=>({ok:false,status:409,json:async()=>({ok:false,code:'attempt_expired',error:'Expiró'})}));await h.submit();const expired=h.requests[0].body.attempt_id;await h.submit();assert.notEqual(h.requests[1].body.attempt_id,expired);
 h=harness();h.setResponder(async()=>({ok:true,json:async()=>({ok:true,order_id:'known-order',receipt_url:'/pago/exito?order=known-order'})}));await h.submit();assert.equal(h.redirects[0],'https://www.zeuzdnc.com/pago/exito?order=known-order');assert.equal(JSON.parse(h.storage.get('zeuz_checkout_attempt_v1')).orderId,'known-order');
 for(const receipt_url of ['https://evil.example/pago/exito?order=known-order','/pago/exito?order=other-order','/pago/exito?order=known-order&next=https://evil.example','/pago/exito?order=known-order#fake','/pago/fallo?order=known-order']) {
  h=harness();h.setResponder(async()=>({ok:true,json:async()=>({ok:true,order_id:'known-order',receipt_url})}));await h.submit();assert.equal(h.redirects.length,0);assert.match(h.error.textContent,/dirección de pago/);
 }
 console.log('PASS: 14 checkout cases — payload, no PII, retry identity, blocked storage, price reconfirmation, double submit, redirect validation, cart-change abort, expired attempt rotation, owned receipt recovery, receipt URL rejection.');
})().catch(error=>{console.error(error);process.exitCode=1;});
