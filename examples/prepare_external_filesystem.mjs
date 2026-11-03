// Transpile the pinned sources without executing their build/install scripts.
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const [vendor, runtime] = process.argv.slice(2);
const require = createRequire(path.join(runtime, 'package.json'));
const ts = require('typescript');
for (const era of ['old', 'new']) {
  fs.mkdirSync(path.join(runtime, era), {recursive: true});
  for (const name of ['index', 'path-validation', 'roots-utils', 'path-utils']) {
    const source = fs.readFileSync(path.join(vendor, era, name + '.ts'), 'utf8');
    const {outputText} = ts.transpileModule(source, {
      compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022},
    });
    fs.writeFileSync(path.join(runtime, era, name + '.js'), outputText);
  }
}
