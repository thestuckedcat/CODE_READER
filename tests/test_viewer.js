// Optional DOM integration test: npm install --no-save linkedom@0.18.12
// node tests/test_viewer.js /path/to/fixture-overview.html
// Runs real viewer handlers; does not claim browser layout validation.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {parseHTML}=require('linkedom');
const html=fs.readFileSync(process.argv[2],'utf8');const {window}=parseHTML(html),document=window.document;
const script=html.split('<script>')[1].split('</script>')[0];
vm.runInNewContext(script,{document,Blob,URL,setTimeout,console,Map,Set,JSON});
function selectFunction(name){const input=document.getElementById('search');input.value=name;input.oninput();const b=document.querySelector('#list button');assert.ok(b);b.onclick();}
selectFunction('leaf');
for(const option of document.querySelectorAll('#direction option'))option.selected=option.value==='up';
document.getElementById('direction').onchange();document.getElementById('paths').onclick();
const choices=document.getElementById('path_choices').textContent;
assert.ok(choices.includes('sdk_entry'),choices);assert.ok(choices.includes('alternate'),choices);assert.ok(choices.includes('最上端'),choices);
selectFunction('callback_entry');
for(const option of document.querySelectorAll('#direction option'))option.selected=option.value==='down';
document.getElementById('direction').onchange();
const detail=document.querySelector('#tree details');detail.open=true;detail.dispatchEvent(new window.Event('toggle'));
assert.ok(document.getElementById('tree').textContent.includes('间接目标未确定'));
selectFunction('sdk_entry');
assert.ok(document.getElementById('detail').textContent.includes('parameters'));
assert.ok(document.getElementById('objects').textContent.includes('settings'));
selectFunction('locked_write');
assert.ok(document.getElementById('detail').textContent.includes('锁事件 2'));
assert.ok(document.getElementById('locks').textContent.includes('shared_counter'));
assert.ok(document.getElementById('locks').textContent.includes('potential_race'));
console.log('PASS: viewer search, function details, paths, unresolved boundary, objects, locks and shared-state warning (DOM; not browser layout).');
