import { defineConfig } from 'orval';
export default defineConfig({
  margin: {
    input: '../contracts/openapi.json',
    hooks: {afterAllFilesWrite: 'prettier --write'},
    output: {
      target: './src/api/generated/endpoints.ts',
      schemas: './src/api/generated/models',
      mode: 'tags-split',
      client: 'react-query',
      httpClient: 'fetch',
      clean: true,
      override: {
        mutator: { path: './src/api/transport.ts', name: 'apiFetch' },
        fetch: { includeHttpResponseReturnType: false },
      },
    },
  },
});
