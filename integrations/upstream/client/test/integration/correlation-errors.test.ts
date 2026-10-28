import { afterEach, describe, expect, it } from "vitest";
import http from "node:http";
import { ProHttpBackend, AuthError, CorrelationFailed, NetworkError, SchemaInvalid, InsecureDefaultError, normalizeCampaignStatus } from "../../src/index.js";
import { readSse } from "../../src/util/sse.js";
import { httpRequest } from "../../src/util/http.js";
import type { CorrelationHandle } from "../../src/contract.js";

let server: http.Server | undefined;
afterEach(async () => { if (server) { server.closeAllConnections(); await new Promise<void>(resolve=>server!.close(()=>resolve())); server=undefined; } });
async function start(reply: (route: string, req: http.IncomingMessage, res: http.ServerResponse) => void) {
  const requests: string[]=[];
  server=http.createServer((req,res)=>{req.resume();const route=new URL(req.url!,"http://localhost").pathname;requests.push(route);reply(route,req,res);});
  await new Promise<void>(resolve=>server!.listen(0,"127.0.0.1",resolve));
  const url=`http://127.0.0.1:${(server.address() as {port:number}).port}`;
  return {url,requests,backend:new ProHttpBackend({baseUrl:url,token:"fixture-token",timeoutMs:1000})};
}
const send=(res:http.ServerResponse,body:unknown,status=200)=>{res.writeHead(status,{"Content-Type":"application/json"});res.end(JSON.stringify(body));};
const handle=():CorrelationHandle=>({edition:"pro",runId:"run_mine",campaignId:null,nonce:"test",preCampaignIds:[],startedAtMs:0});

describe("Explicit HTTP campaign identity and failure boundaries",()=>{
 it("retains launch identity without listing or guessing from unrelated campaigns",async()=>{
  const {backend,requests}=await start((route,req,res)=>send(res,req.method==="POST"?{run_id:"run_mine",campaign_id:"camp_mine"}:route.endsWith("camp_mine")?{data:{id:"camp_mine",status:"completed"}}:{data:[{id:"camp_other",status:"completed"}]}));
  const launched=await backend.launchCampaign({target:"owned.invalid"});expect(launched.campaignId).toBe("camp_mine");
  expect((await backend.getCampaignStatus(launched.correlation)).id).toBe("camp_mine");
  expect(requests).toEqual(["/api/v1/run/campaign","/api/v1/campaigns/camp_mine"]);
 });
 it("uses an explicit run record for older launch responses",async()=>{
  const {backend}=await start((_route,_req,res)=>send(res,{id:"run_mine",campaign_id:"camp_mine",status:"running"}));
  expect(await backend.resolveCampaignId(handle())).toBe("camp_mine");
 });
 it("rejects a different run identity rather than following its campaign",async()=>{
  const {backend}=await start((_route,_req,res)=>send(res,{id:"run_other",campaign_id:"camp_other"}));
  await expect(backend.resolveCampaignId(handle())).rejects.toBeInstanceOf(CorrelationFailed);
 });
 it("uses complete root session identity and never a shared eight-character prefix",async()=>{
  const {backend}=await start((route,_req,res)=>{
   if(route==="/api/v1/run/run_mine")return send(res,{},404);
   if(route.includes("/run/logs/"))return send(res,{data:[{type:"run_started",sessionID:"ses_abcdefgh_second_complete_root"}]});
   send(res,{data:[{id:"camp_first",session_id:"ses_abcdefgh_first_complete_root"},{id:"camp_second",session_id:"ses_abcdefgh_second_complete_root"}]});
  });
  expect(await backend.resolveCampaignId(handle())).toBe("camp_second");
 });
 it("does not bind a single unrelated new campaign or a child session log",async()=>{
  const {backend,requests}=await start((route,_req,res)=>{
   if(route==="/api/v1/run/run_mine")return send(res,{},404);
   if(route.includes("/run/logs/"))return send(res,{data:[{type:"step",sessionID:"ses_child"}]});
   send(res,{data:[{id:"camp_unrelated",session_id:"ses_child",status:"completed"}]});
  });
  expect(await backend.resolveCampaignId(handle())).toBeNull();expect(requests).not.toContain("/api/v1/campaigns");
 });
 it("fails for ambiguous complete roots instead of choosing the first",async()=>{
  const {backend}=await start((route,_req,res)=>{
   if(route==="/api/v1/run/run_mine")return send(res,{},404);
   if(route.includes("/run/logs/"))return send(res,{data:[{type:"run_started",sessionID:"ses_same_complete"}]});
   send(res,{data:[{id:"one",session_id:"ses_same_complete"},{id:"two",session_id:"ses_same_complete"}]});
  });await expect(backend.resolveCampaignId(handle())).rejects.toBeInstanceOf(CorrelationFailed);
 });
 it("does not swallow auth or server errors while correlating",async()=>{
  let status=401;const {backend}=await start((_route,_req,res)=>send(res,{detail:"PRIVATE-SERVER-BODY"},status));
  await expect(backend.resolveCampaignId(handle())).rejects.toBeInstanceOf(AuthError);
  status=500;await expect(backend.resolveCampaignId(handle())).rejects.toMatchObject({code:"NETWORK"});
 });
 it("rejects a terminal run with no campaign identity",async()=>{
  const {backend}=await start((_route,_req,res)=>send(res,{id:"run_mine",status:"interrupted"}));
  await expect(backend.resolveCampaignId(handle())).rejects.toBeInstanceOf(CorrelationFailed);
 });
 it("rejects wrong-typed or missing launch identities",async()=>{
  let body:unknown={run_id:42};const {backend}=await start((_route,_req,res)=>send(res,body));
  await expect(backend.launchCampaign({target:"owned.invalid"})).rejects.toBeInstanceOf(SchemaInvalid);
  body={};await expect(backend.launchCampaign({target:"owned.invalid"})).rejects.toBeInstanceOf(SchemaInvalid);
 });
 it("rejects wrong campaign/finding/report identities",async()=>{
  const {backend}=await start((route,_req,res)=>send(res,route.endsWith("/report")?{campaign_id:"wrong",content:"wrong report"}:{data:{id:"wrong"}}));
  await expect(backend.getCampaign("mine")).rejects.toBeInstanceOf(SchemaInvalid);
  await expect(backend.getFinding("mine")).rejects.toBeInstanceOf(SchemaInvalid);
  await expect(backend.getReport("mine")).rejects.toBeInstanceOf(SchemaInvalid);
 });
 it("does not treat a malformed or missing list envelope as zero findings",async()=>{
  let malformed=false;const {backend}=await start((_route,_req,res)=>{if(malformed){res.writeHead(200);res.end("{");}else send(res,{});});
  await expect(backend.listCampaigns()).rejects.toBeInstanceOf(SchemaInvalid);
  await expect(backend.listFindings({})).rejects.toBeInstanceOf(SchemaInvalid);
  malformed=true;await expect(backend.listCampaigns()).rejects.toBeInstanceOf(SchemaInvalid);
 });
 it("applies its timeout through the entire body read",async()=>{
  const {url,requests}=await start((_route,_req,res)=>{res.writeHead(200,{"Content-Type":"application/json"});res.write('{"data":');});
  await expect(httpRequest(url+"/slow",{timeoutMs:250})).rejects.toBeInstanceOf(NetworkError);expect(requests).toEqual(["/slow"]);
 });
 it("does not forward credentials or launch bodies through redirects",async()=>{
  const {url,requests}=await start((route,_req,res)=>{if(route==="/redirect"){res.writeHead(307,{Location:"/destination"});res.end();}else send(res,{});});
  await expect(httpRequest(url+"/redirect",{method:"POST",body:{password:"PRIVATE"},token:"PRIVATE-TOKEN"})).rejects.toMatchObject({code:"NETWORK"});
  expect(requests).toEqual(["/redirect"]);
 });
});

const collect = async (events: AsyncIterable<unknown>) => { const rows: unknown[] = []; for await (const event of events) rows.push(event); return rows; };
describe("Authenticated reads and bounded streaming", () => {
 it("logs in for read-only operations and preserves credentials in the bearer header", async () => {
  const {url,requests}=await start((route,req,res)=>{
   if(route.endsWith("/auth/login")) return send(res,{token:"read-token"});
   expect(req.headers.authorization).toBe("Bearer read-token");send(res,{data:[]});
  });
  await new ProHttpBackend({baseUrl:url,username:"fixture",password:"fixture"}).listCampaigns();
  expect(requests).toEqual(["/api/v1/auth/login","/api/v1/campaigns"]);
 });
 it("does not cache a token rejected by the default-password policy", async () => {
  const {url,requests}=await start((_route,_req,res)=>send(res,{token:"unsafe-token",must_change_password:true}));
  const backend=new ProHttpBackend({baseUrl:url,username:"fixture",password:"fixture"});
  await expect(backend.listCampaigns()).rejects.toBeInstanceOf(InsecureDefaultError);
  await expect(backend.listCampaigns()).rejects.toBeInstanceOf(InsecureDefaultError);
  expect(requests).toEqual(["/api/v1/auth/login","/api/v1/auth/login"]);
 });
 it("keeps unknown/incomplete statuses nonterminal and classifies interrupted runs as failures",()=>{
  expect(normalizeCampaignStatus("incomplete")).toBe("unknown");
  expect(normalizeCampaignStatus("awaiting_review")).toBe("unknown");
  for(const raw of ["timed_out","interrupted"])expect(normalizeCampaignStatus(raw)).toBe("failed");
  expect(normalizeCampaignStatus("aborted")).toBe("stopped");
 });
 it("parses CRLF frames even when the delimiter is split across chunks",async()=>{
  const {url}=await start((_route,_req,res)=>{
   res.writeHead(200,{"Content-Type":"text/event-stream"});res.write('data: {"type":"step"}\r');
   setTimeout(()=>res.end('\n\r\ndata: {"type":"run_completed"}\r\n\r\n'),10);
  });
  expect(await collect(readSse(url))).toEqual([{type:"step"},{type:"run_completed"}]);
 });
 it("surfaces SSE authorization, malformed JSON and partial frames without leaking payloads",async()=>{
  let mode="auth";const {url}=await start((_route,_req,res)=>{
   if(mode==="auth")return send(res,{detail:"PRIVATE"},403);
   res.writeHead(200,{"Content-Type":"text/event-stream"});res.end(mode==="json"?'data: PRIVATE\n\n':'data: {"type":"step"}');
  });
  await expect(collect(readSse(url))).rejects.toBeInstanceOf(AuthError);
  mode="json";await expect(collect(readSse(url))).rejects.toMatchObject({code:"SCHEMA_INVALID",message:"SSE returned malformed JSON."});
  mode="partial";await expect(collect(readSse(url))).rejects.toBeInstanceOf(SchemaInvalid);
 });
 it("fails when a progress stream closes before a terminal event",async()=>{
  const {backend}=await start((_route,_req,res)=>{res.writeHead(200,{"Content-Type":"text/event-stream"});res.end('data: {"type":"step"}\n\n');});
  await expect(collect(backend.streamProgress(handle()))).rejects.toBeInstanceOf(NetworkError);
 });
 it("bounds an idle stream and closes its socket when the consumer exits early",async()=>{
  let closed=false;const {url}=await start((_route,_req,res)=>{
   res.on("close",()=>{closed=true;});res.writeHead(200,{"Content-Type":"text/event-stream"});res.write('data: {"type":"step"}\n\n');
  });
  await expect(collect(readSse(url,{timeoutMs:100}))).rejects.toBeInstanceOf(NetworkError);
  closed=false;for await(const event of readSse(url)){expect(event).toEqual({type:"step"});break;}
  await new Promise(resolve=>setTimeout(resolve,30));expect(closed).toBe(true);
 });
 it("rejects conflicting stream identities",async()=>{
  const {backend}=await start((_route,_req,res)=>{res.writeHead(200,{"Content-Type":"text/event-stream"});res.end('data: {"type":"run_completed","run_id":"other"}\n\n');});
  await expect(collect(backend.streamProgress(handle()))).rejects.toBeInstanceOf(CorrelationFailed);
 });
 it("honors explicit cancellation and refuses oversized frames and redirects",async()=>{
  let mode="oversize";const {url,requests}=await start((_route,_req,res)=>{
   if(mode==="redirect"){res.writeHead(302,{Location:"/destination"});res.end();return;}
   res.writeHead(200,{"Content-Type":"text/event-stream"});res.end('data: '+"x".repeat(1024*1024));
  });
  await expect(collect(readSse(url))).rejects.toBeInstanceOf(SchemaInvalid);
  mode="redirect";await expect(collect(readSse(url))).rejects.toBeInstanceOf(NetworkError);
  const abort=new AbortController();abort.abort();expect(await collect(readSse(url,{signal:abort.signal}))).toEqual([]);
  expect(requests).not.toContain("/destination");
 });
});
