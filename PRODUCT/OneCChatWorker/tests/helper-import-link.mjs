// Link the installed entrypoint and its complete static module graph, without
// evaluating helper code, reading admission, starting a process or networking.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath,pathToFileURL} from 'node:url';

const root=path.resolve(process.argv[2]),modules=new Map(),files=[];
async function load(url){
  if(modules.has(url))return modules.get(url);
  if(url.startsWith('node:')){
    const namespace=await import(url),names=Object.keys(namespace);
    const module=new vm.SyntheticModule(names,function(){for(const name of names)this.setExport(name,namespace[name]);},{identifier:url});
    modules.set(url,module);return module;
  }
  const file=fileURLToPath(url);
  assert(file.startsWith(root+path.sep),'module outside isolated install root');
  const module=new vm.SourceTextModule(await fs.readFile(file,'utf8'),{identifier:url});
  modules.set(url,module);files.push(path.relative(root,file).replaceAll(path.sep,'/'));return module;
}
const entry=await load(pathToFileURL(path.join(root,'helper','hosted-helper.mjs')).href);
await entry.link(async(specifier,ref)=>{
  assert(specifier.startsWith('node:')||specifier.startsWith('.'),'unexpected external helper dependency');
  return load(specifier.startsWith('node:')?specifier:new URL(specifier,ref.identifier).href);
});
assert.equal(entry.status,'linked');
assert(files.includes('helper/helper-https-pull.mjs'));
assert(files.includes('helper/https-pull-auth.mjs'));
assert(files.includes('helper/task-checkpoint-store.mjs'));
console.log(JSON.stringify({result:'PASS',evaluated:false,static_imports:files.sort()}));
