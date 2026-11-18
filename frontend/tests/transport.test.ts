import assert from 'node:assert/strict';
import {afterEach, test} from 'node:test';
import {ApiError, apiFetch} from '../src/api/transport.ts';
import {createBook} from '../src/api/generated/books/books.ts';
import {uploadReading, listReadings} from '../src/api/generated/readings/readings.ts';
import {uploadCaptureBatch} from '../src/api/generated/capture/capture.ts';
const originalFetch=globalThis.fetch;
afterEach(() => {globalThis.fetch=originalFetch;});

test('generated JSON request preserves owner credentials and returns parsed data',async () => {
  globalThis.fetch=async (url, init) => {
    assert.equal(url,'/api/books'); assert.equal(init?.method,'POST');
    assert.equal(init?.credentials,'same-origin');
    assert.equal(new Headers(init?.headers).get('Content-Type'),'application/json');
    assert.deepEqual(JSON.parse(String(init?.body)),{title:'A book'});
    return Response.json({id:'book-1',title:'A book'});
  };
  assert.equal((await createBook({title:'A book'})).id,'book-1');
});

test('generated upload sends multipart with a browser-owned boundary',async () => {
  globalThis.fetch=async (url,init) => {
    assert.equal(url,'/api/books/book-1/sessions');
    assert(init?.body instanceof FormData);
    assert.equal(new Headers(init.headers).get('Content-Type'),null);
    assert.equal(init.body.get('page_label'),'24–25');
    assert(init.body.get('image') instanceof Blob);
    return Response.json({id:'reading-1'});
  };
  assert.equal((await uploadReading('book-1',{image:new Blob(['photo']),page_label:'24–25'})).id,'reading-1');
});

test('generated queries propagate AbortSignal',async () => {
  const controller=new AbortController();
  globalThis.fetch=async (url,init) => {
    assert.equal(url,'/api/books/book-1/sessions');
    assert.equal(init?.signal,controller.signal);
    return Response.json([]);
  };
  assert.deepEqual(await listReadings('book-1',{signal:controller.signal}),[]);
});

test('generated batch upload preserves ordered files and page labels',async () => {
  globalThis.fetch=async (url,init) => {
    assert.equal(url,'/api/capture/test-token/batch');
    assert(init?.body instanceof FormData);
    assert.equal(new Headers(init.headers).get('Content-Type'),null);
    assert.deepEqual(init.body.getAll('page_labels'),['12–13','14–15']);
    const files=init.body.getAll('images');
    assert.equal(files.length,2);
    assert(files[0] instanceof Blob && files[1] instanceof Blob);
    assert.equal(await files[0].text(),'first');
    assert.equal(await files[1].text(),'second');
    return Response.json({batch_id:'batch-1',session_ids:['one','two']},{status:201});
  };
  const result=await uploadCaptureBatch('test-token',{images:[new Blob(['first']),new Blob(['second'])],page_labels:['12–13','14–15']});
  assert.deepEqual(result.session_ids,['one','two']);
});

test('transport surfaces domain and validation failures',async () => {
  globalThis.fetch=async () => Response.json({detail:[{msg:'Choose a photograph'}]},{status:422});
  await assert.rejects(()=>apiFetch('/api/test'),(error: unknown)=>error instanceof ApiError && error.status===422 && error.message==='Choose a photograph');
});
