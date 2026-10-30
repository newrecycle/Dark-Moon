// Executes actual production code against a controlled device interface.
// Permission/session/resource acceptance; no physical headset rendering claim.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('mcp/community/static/app.js','utf8');
const start=source.indexOf('async function startVR('),end=source.indexOf('\nlock();',start);
assert.ok(start>0&&end>start);
function fixture({pending=false,compile=true,link=true,pendingInit=null,endReject=false}={}){
 let resolve,release,enteredResolve,requests=0,ended=0,cleaned=0,frames=[];
 const gate=new Promise(r=>release=r),entered=new Promise(r=>enteredResolve=r);
 const phase=async name=>{if(name===pendingInit){enteredResolve();await gate;}return {};};
 const session=new EventTarget();
 Object.assign(session,{renderState:{},updateRenderState(value){this.renderState=value;},
   requestReferenceSpace:()=>phase('space'),requestAnimationFrame(frame){frames.push(frame);},
   end:async()=>{ended++;if(endReject)throw new Error('fixture end rejection');session.dispatchEvent(new Event('end'));}});
 const gl=new Proxy({makeXRCompatible:()=>phase('compatible'),getShaderParameter:()=>compile,
   getProgramParameter:()=>link,getProgramInfoLog:()=> 'fixture link failure',
   getShaderInfoLog:()=> 'fixture compile failure',createShader:()=>({}),createProgram:()=>({}),createBuffer:()=>({}),
   deleteShader:()=>{cleaned++;},deleteBuffer:()=>{cleaned++;},deleteProgram:()=>{cleaned++;}},
   {get:(target,key)=>target[key]??(()=>{})});
 const context={AbortController,Float32Array,Map,document:{createElement:()=>({getContext:()=>gl})},
   navigator:{xr:{requestSession:()=>{requests++;return pending?new Promise(r=>resolve=r):Promise.resolve(session);}}},
   XRWebGLLayer:class{constructor(){this.framebuffer=null;}getViewport(){return {x:0,y:0,width:1,height:1};}}};
 vm.createContext(context);vm.runInContext(source.slice(start,end)+'\nglobalThis.start=startVR;',context);
 return {run:context.start,session,ready:()=>resolve(session),entered,release,
   get requests(){return requests;},get ended(){return ended;},get cleaned(){return cleaned;},frames};
}
(async()=>{
 let f=fixture(),control=new AbortController();control.abort();await f.run([],[],control.signal);assert.equal(f.requests,0);
 f=fixture({pending:true});control=new AbortController();let running=f.run([],[],control.signal);
 control.abort();f.ready();await running;assert.equal(f.ended,1);
 for(const pendingInit of ['compatible','space']){
   f=fixture({pendingInit});control=new AbortController();running=f.run([],[],control.signal);
   await f.entered;control.abort();f.release();await running;
   assert.equal(f.ended,1);assert.equal(f.frames.length,0);assert.equal(f.cleaned,0,'abort cannot allocate resources after cleanup');
 }
 f=fixture({pendingInit:'space'});control=new AbortController();running=f.run([],[],control.signal);
 await f.entered;f.session.dispatchEvent(new Event('end'));f.release();await running;assert.equal(f.frames.length,0);assert.equal(f.cleaned,0);
 for(const endReject of [false,true]){
   f=fixture({endReject});control=new AbortController();await f.run([{id:'n',p:[0,0,0]}],[],control.signal);
   assert.equal(f.frames.length,1);control.abort();assert.equal(f.ended,1);assert.equal(f.cleaned,4);
   const count=f.frames.length;f.frames[0](0,{getViewerPose:()=>null});assert.equal(f.frames.length,count);
 }
 f=fixture({compile:false});control=new AbortController();await assert.rejects(f.run([],[],control.signal));assert.equal(f.ended,1);assert.ok(f.cleaned>=2);
 f=fixture({link:false});control=new AbortController();await assert.rejects(f.run([],[],control.signal));assert.equal(f.ended,1);assert.equal(f.cleaned,3);
 console.log('PASS production XR: permission/init/view abort, external end, rejected end, no stale allocations/frames, shader compile/link cleanup');
})().catch(error=>{console.error(error);process.exitCode=1;});
