// SPDX-License-Identifier: MPL-2.0
import {resolve,dirname} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';

async function main(){
  const root=resolve(process.argv[2]),output=resolve(process.argv[3]);
  const {build}=await import(pathToFileURL(resolve(root,'node_modules/esbuild/lib/main.js')).href);
  await build({entryPoints:[resolve(dirname(fileURLToPath(import.meta.url)),'native_viewer.tsx')],outfile:output,
    absWorkingDir:root,bundle:true,platform:'browser',format:'iife',globalName:'OpenIndustriesNative',
    target:'es2022',jsx:'automatic',minify:true,legalComments:'eof',nodePaths:[resolve(root,'node_modules')],
    define:{'import.meta.env':'{}','process.env.NODE_ENV':'"production"'},
    plugins:[{name:'native-openindustries',setup(builder:any){
      builder.onResolve({filter:/^openindustries-viewer$/},()=>({path:resolve(root,'src/components/workspace-viewer.tsx')}));
      builder.onResolve({filter:/^openindustries-workspace$/},()=>({path:resolve(root,'src/lib/workspace.ts')}));
      builder.onResolve({filter:/^openindustries-world$/},()=>({path:resolve(root,'src/lib/world.ts')}));
      builder.onResolve({filter:/^openindustries-form$/},()=>({path:resolve(root,'src/lib/form.ts')}));
      builder.onResolve({filter:/^openindustries-gif$/},()=>({path:resolve(root,'src/lib/gif.ts')}));
    }}]});
}
main().catch(error=>{console.error(error);process.exitCode=1;});
