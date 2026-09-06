// node tests/test_flow_viewer.js /path/to/flow_fixture.html (linkedom required)
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {parseHTML}=require('linkedom');
const html=fs.readFileSync(process.argv[2],'utf8'),{document}=parseHTML(html).window;
vm.runInNewContext(html.split('<script>')[1].split('</script>')[0],{document,Blob,URL,setTimeout,console,Map,Set,JSON});
function click(text,container='#detail'){const b=[...document.querySelectorAll(container+' button')].find(b=>b.textContent.includes(text));assert.ok(b,text);b.onclick();}
const search=document.getElementById('search');search.value='sdk_flow';search.oninput();click('sdk_flow','#list');
click('追踪参数 input');
let detail=document.getElementById('detail');assert.ok(detail.textContent.includes('参数计算链 / 条件'));
const flow=detail.lastElementChild;
assert.ok(flow.textContent.includes('twice(input)'));assert.ok(flow.textContent.includes('control_sources'));
click('继续追踪实参', '#detail');assert.ok(detail.textContent.includes('value * 2'));
click('返回值来源');assert.ok(detail.textContent.includes('返回值来源 / 条件'));
assert.ok(document.getElementById('status').textContent.includes('Clang CFG'));
console.log('PASS: CFG parameter trace, call argument navigation, return provenance (DOM only).');
