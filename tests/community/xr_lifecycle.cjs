// Execute production XR lifecycle code against a controlled device interface.
// This is permission/session/resource acceptance, not physical headset rendering.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('mcp/community/static/app.js','utf8');
const start=source.indexOf('async function startVR('),end=source.indexOf('\nlock();',start);
assert.ok(start>0&&end>start);
function fixture({pending=false,compile=true}={}){
 let resolve,requests=0,ended=0,cleaned=0,frames=[];
 const session=new EventTarget();
 Object.assign(session,{renderState:{},updateRenderState(value){this.renderState=value;},requestReferenceSpace:async()=>({}),
   requestAnimationFrame(frame){frames.push(frame);},end:async()=>{ended++;session.dispatchEvent(new Event('end'));}});
 const gl=new Proxy({makeXRCompatible:async()=>{},getShaderParameter:()=>compile,getShaderInfoLog:()=> 'fixture compile failure',
   createShader:()=>({}),createProgram:()=>({}),createBuffer:()=>({}),
   deleteShader:()=>{cleaned++;},deleteBuffer:()=>{cleaned++;},deleteProgram:()=>{cleaned++;}},
   {get:(target,key)=>target[key]??(()=>{})});
 const context={AbortController,Float32Array,Map,document:{createElement:()=>({getContext:()=>gl})},
   navigator:{xr:{requestSession:()=>{requests++;return pending?new Promise(r=>resolve=r):Promise.resolve(session);}}},
   XRWebGLLayer:class{constructor(){this.framebuffer=null;}getViewport(){return {x:0,y:0,width:1,height:1};}}};
 vm.createContext(context);vm.runInContext(source.slice(start,end)+'\nglobalThis.start=startVR;',context);
 return {run:context.start,session,ready:()=>resolve(session),get requests(){return requests;},get ended(){return ended;},get cleaned(){return cleaned;},frames};
}
(async()=>{
 let f=fixture(),control=new AbortController();control.abort();await f.run([],[],control.signal);assert.equal(f.requests,0);
 f=fixture({pending:true});control=new AbortController();const running=f.run([],[],control.signal);control.abort();f.ready();await running;assert.equal(f.ended,1);
 f=fixture();control=new AbortController();await f.run([{id:'n',p:[0,0,0]}],[],control.signal);assert.equal(f.frames.length,1);control.abort();assert.equal(f.ended,1);assert.equal(f.cleaned,4);
 const count=f.frames.length;f.frames[0](0,{getViewerPose:()=>null});assert.equal(f.frames.length,count);
 f=fixture({compile:false});control=new AbortController();await assert.rejects(f.run([],[],control.signal));assert.equal(f.ended,1);assert.ok(f.cleaned>=2);
 console.log('PASS production XR lifecycle: pre-abort, delayed permission, view abort, no post-end frames, shader-failure cleanup');
})().catch(error=>{console.error(error);process.exitCode=1;});
