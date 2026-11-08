// ST-N01/F04/F05/F06：执行实际页面脚本，按任意字节分包并核对DOM清屏。
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
const script=readFileSync('app/templates/_sessions_script.html','utf8');
const encode=new TextEncoder();
const frame=(event,data)=>`event: ${event}\ndata: ${JSON.stringify({code:0,request_id:'synthetic',data})}\n\n`;
const meta=frame('meta',{}),delta=frame('delta',{text:'电压24伏🙂'}),done=frame('done',{message_id:'message'});
async function run(bytes,blocks,success){
  const nodes=new Map();let resolveEnd;const finished=new Promise(resolve=>resolveEnd=resolve);
  const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',hidden:true,disabled:false,append(){},replaceChildren(){},focus(){},querySelector(){return node('submit');}});return nodes.get(id);};
  node('session-question').value='电压问题';node('session-retrieval').value='keyword';
  let reads=0;
  const fetch=async path=>{
    if(path.endsWith('/messages'))return new Response(new ReadableStream({start(c){let pos=0;for(const size of blocks){c.enqueue(bytes.slice(pos,pos+size));pos+=size;}if(pos<bytes.length)c.enqueue(bytes.slice(pos));c.close();}}),{headers:{'Content-Type':'text/event-stream'}});
    const data=path.includes('assistants')?{items:[{id:'assistant',name:'合成助手',enabled:true}],total:1}:path.includes('chapters')?{items:[]}:path.includes('sessions?')?{items:[],total:0}:{messages:[],total:0};
    if(path.includes('sessions/session?'))reads++;
    return new Response(JSON.stringify({code:0,data}));
  };
  const context={target:'session',document:{getElementById:node,createElement:()=>({append(){}})},fetch,crypto:webcrypto,AbortController,AbortSignal,TextDecoder,setTimeout,clearTimeout,location:{assign(){}}};
  vm.runInNewContext(script,context);
  await new Promise(resolve=>setImmediate(resolve));
  await node('session-send').onsubmit({preventDefault(){},submitter:node('send')});
  assert.equal(node('session-preview').textContent,'');assert.equal(node('session-preview').hidden,true);
  assert.equal(node('session-status').textContent.includes('生成已完成并保存'),success);
  assert.equal(node('send').disabled,false);assert.equal(node('session-cancel').disabled,true);
  if(!success)assert.equal(reads,1,'失败不得作为成功重新读取');
  resolveEnd();await finished;
}
const valid=encode.encode(meta+delta+done);
// 每一个字节切点均包括中文、emoji多字节UTF-8、CRLF以及帧边界。
for(let split=1;split<valid.length;split++)await run(valid,[split],true);
await run(valid,Array(valid.length).fill(1),true);
await run(encode.encode((meta+delta+done).replaceAll('\n','\r\n')),Array(valid.length*2).fill(1),true);
for(const value of [meta+delta,meta+delta+'event: error\ndata: {"code":1500,"message":"依赖故障","request_id":"synthetic"}\n\n',delta+done,meta+done,meta+delta+done+done,meta+delta+'event: delta\ndata: broken\n\n',meta+delta+'partial'])await run(encode.encode(value),[1,7,31],false);
await run(new Uint8Array([...encode.encode(meta+delta),0xff]),[1],false);
console.log(JSON.stringify({scenario:'ST-N01/F04/F05/F06',split_points:valid.length-1,bytewise_utf8:true,crlf:true,negative_cases:8,preview_cleared:true}));
