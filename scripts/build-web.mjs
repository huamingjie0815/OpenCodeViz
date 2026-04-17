import { cpSync, existsSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

const src = resolve("src/codeviz/web");
const dest = resolve("dist/web");
const vendorSrc = resolve("node_modules/d3/dist/d3.min.js");
const markedSrc = resolve("node_modules/marked/marked.min.js");
const vendorDest = resolve("src/codeviz/web/vendor");
const builtVendorDest = resolve("dist/web/vendor");

mkdirSync(dest, { recursive: true });
cpSync(src, dest, { recursive: true });
if (existsSync(vendorSrc) || existsSync(markedSrc)) {
  mkdirSync(vendorDest, { recursive: true });
  mkdirSync(builtVendorDest, { recursive: true });
}
if (existsSync(vendorSrc)) {
  cpSync(vendorSrc, resolve(vendorDest, "d3.min.js"));
  cpSync(vendorSrc, resolve(builtVendorDest, "d3.min.js"));
}
if (existsSync(markedSrc)) {
  cpSync(markedSrc, resolve(vendorDest, "marked.min.js"));
  cpSync(markedSrc, resolve(builtVendorDest, "marked.min.js"));
}
console.log(`copied ${src} -> ${dest}`);
