const fs = require('fs'),
  ts = require('../apps/web/node_modules/typescript');
require.extensions['.ts'] = (mod, file) =>
  mod._compile(
    ts.transpileModule(fs.readFileSync(file, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText,
    file,
  );

const Module = require('module'),
  compile = Module.prototype._compile;
Module.prototype._compile = function (code, file) {
  if (file.endsWith('.ts')) {
    this.filename = file;
    this.paths = Module._nodeModulePaths(require('path').dirname(file));
  }
  return compile.call(this, code, file);
};
