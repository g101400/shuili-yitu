#!/usr/bin/env node
/* sec_crypt.js —— 内部数据/凭据加密工具（AES-256-GCM + PBKDF2-SHA256）
 * 用法：node sec_crypt.js <out.js> <globalVarName> <passphrase> <file1> [file2 ...]
 * 输出：window.<globalVarName> = {"alg":"AES-GCM-256","iter":120000,"s":"<salt b64>","i":"<iv b64>","c":"<ct b64>"};
 * 载荷明文为 JSON: {"f":[["data.js","<原文>"], ...]}
 */
const fs = require('fs');
const crypto = require('crypto');

const [out, varName, pass, ...files] = process.argv.slice(2);
if (!out || !varName || !pass || !files.length) {
  console.error('usage: node sec_crypt.js <out.js> <varName> <pass> <files...>');
  process.exit(2);
}
const ITER = 120000, KEYLEN = 32, IVLEN = 12, SALTLEN = 16;
const salt = crypto.randomBytes(SALTLEN);
const iv = crypto.randomBytes(IVLEN);
const payload = JSON.stringify({ f: files.map(p => [require('path').basename(p), fs.readFileSync(p, 'utf8')]) });
const key = crypto.pbkdf2Sync(pass, salt, ITER, KEYLEN, 'sha256');
const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
const enc = Buffer.concat([cipher.update(Buffer.from(payload, 'utf8')), cipher.final()]);
const tag = cipher.getAuthTag();
const ct = Buffer.concat([enc, tag]); // GCM tag 16B 追加在尾部，与 WebCrypto 默认一致
const js = 'window.' + varName + ' = ' + JSON.stringify({
  alg: 'AES-GCM-256', iter: ITER, ks: KEYLEN * 8,
  s: salt.toString('base64'), i: iv.toString('base64'), c: ct.toString('base64')
}) + ';\n';
fs.writeFileSync(out, js, 'utf8');
console.log('OK ' + out + '  ' + (js.length / 1024).toFixed(0) + 'KB  files=' + files.map(f => require('path').basename(f)).join(','));
