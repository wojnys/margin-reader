import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  envDir: false, // Frontend uses same-origin APIs; private dotenv configuration stays server-side.
  plugins: [
    react(),
    {
      name: "local-owner-bootstrap",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          const peer = req.socket.remoteAddress;
          if (
            req.url?.startsWith("/api/bootstrap") &&
            !["127.0.0.1", "::1", "::ffff:127.0.0.1"].includes(peer || "")
          ) {
            res.statusCode = 403;
            res.end("Open the reading room on localhost on your computer.");
            return;
          }
          next();
        });
      },
    },
  ],
  server: {
    port: 5187,
    strictPort: true,
    proxy: { "/api": { target: "http://127.0.0.1:8017", changeOrigin: false } },
  },
});
