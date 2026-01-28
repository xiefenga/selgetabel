import svgr from "vite-plugin-svgr";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig, loadEnv } from "vite";
import tsconfigPaths from "vite-tsconfig-paths";
import { reactRouter } from "@react-router/dev/vite";

export default defineConfig(({ mode }) => {

  const envs = loadEnv('development', process.cwd(), '')

  const API_BASE_URL = envs.API_BASE_URL;

  return {
    plugins: [tailwindcss(), reactRouter(), tsconfigPaths(), svgr()],
    server: {
      proxy: {
        "/api": {
          target: API_BASE_URL,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
        "/storage": {
          target: 'http://localhost:9000',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/storage/, ""),
        }
      }
    },
  }
});
