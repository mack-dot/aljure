// Optional offline setup. Read verified npm cache entries; do not modify that cache.
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {mkdir, writeFile, readFile, symlink} from 'node:fs/promises';
import {homedir} from 'node:os';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const require=createRequire(import.meta.url);
const npmRoot=execFileSync('npm',['root','-g'],{encoding:'utf8'}).trim();
const cacache=require(require.resolve('cacache',{paths:[resolve(npmRoot,'npm')]}));
const packages=[['react','19.2.4'],['react-dom','19.2.4'],['scheduler','0.27.0'],
 ['typescript','5.9.3'],['esbuild','0.25.12'],['@types/react','19.2.14'],
 ['@types/react-dom','19.2.3'],['csstype','3.2.3'],[`@esbuild/${process.platform}-${process.arch}`,'0.25.12']];
const lock={schema:1,source:'verified npm content-addressed cache',packages:[]};
for (const [name,version] of packages) {
 const base=name.split('/').at(-1);
 const url=`https://registry.npmjs.org/${name}/-/${base}-${version}.tgz`;
 const entry=await cacache.get(resolve(homedir(),'.npm/_cacache'),`make-fetch-happen:request-cache:${url}`);
 const archive=resolve(root,'.cache/npm',`${base}-${version}.tgz`);
 const target=resolve(root,'dashboard/node_modules',name);
 await mkdir(dirname(archive),{recursive:true});await mkdir(target,{recursive:true});
 await writeFile(archive,entry.data);
 execFileSync('tar',['-xzf',archive,'--strip-components=1','-C',target]);
 const meta=JSON.parse(await readFile(resolve(target,'package.json'),'utf8'));
 if(meta.name!==name||meta.version!==version)throw new Error('Cached package identity mismatch');
 lock.packages.push({name,version,url,integrity:entry.integrity});
 if(meta.bin) {
   const bins=typeof meta.bin==='string'?{[base]:meta.bin}:meta.bin;
   await mkdir(resolve(root,'dashboard/node_modules/.bin'),{recursive:true});
   for(const [bin,path] of Object.entries(bins)) {
     try {await symlink(resolve(target,path),resolve(root,'dashboard/node_modules/.bin',bin));}
     catch(e){if(e.code!=='EEXIST')throw e;}
   }
 }
}
await writeFile(resolve(root,'dashboard/offline-dependencies.json'),JSON.stringify(lock,null,2)+'\n');
console.log(`Installed ${packages.length} pinned packages from verified local cache.`);
