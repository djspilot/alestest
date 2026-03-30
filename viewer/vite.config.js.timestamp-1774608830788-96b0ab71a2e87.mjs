// vite.config.js
import { defineConfig } from "file:///sessions/quirky-zealous-meitner/mnt/alestest/viewer/node_modules/vite/dist/node/index.js";
import react from "file:///sessions/quirky-zealous-meitner/mnt/alestest/viewer/node_modules/@vitejs/plugin-react/dist/index.js";
var vite_config_default = defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  build: {
    target: "es2020",
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/react") || id.includes("node_modules/react-dom")) {
            return "react-vendor";
          }
          if (id.includes("node_modules/three") || id.includes("@react-three")) {
            return "viewer-3d";
          }
          if (id.includes("src/ViewerCanvas.jsx") || id.includes("src/StepModel.jsx") || id.includes("src/stepLoader.js")) {
            return "viewer-runtime";
          }
          return void 0;
        }
      }
    }
  }
});
export {
  vite_config_default as default
};
//# sourceMappingURL=data:application/json;base64,ewogICJ2ZXJzaW9uIjogMywKICAic291cmNlcyI6IFsidml0ZS5jb25maWcuanMiXSwKICAic291cmNlc0NvbnRlbnQiOiBbImNvbnN0IF9fdml0ZV9pbmplY3RlZF9vcmlnaW5hbF9kaXJuYW1lID0gXCIvc2Vzc2lvbnMvcXVpcmt5LXplYWxvdXMtbWVpdG5lci9tbnQvYWxlc3Rlc3Qvdmlld2VyXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ZpbGVuYW1lID0gXCIvc2Vzc2lvbnMvcXVpcmt5LXplYWxvdXMtbWVpdG5lci9tbnQvYWxlc3Rlc3Qvdmlld2VyL3ZpdGUuY29uZmlnLmpzXCI7Y29uc3QgX192aXRlX2luamVjdGVkX29yaWdpbmFsX2ltcG9ydF9tZXRhX3VybCA9IFwiZmlsZTovLy9zZXNzaW9ucy9xdWlya3ktemVhbG91cy1tZWl0bmVyL21udC9hbGVzdGVzdC92aWV3ZXIvdml0ZS5jb25maWcuanNcIjtpbXBvcnQgeyBkZWZpbmVDb25maWcgfSBmcm9tICd2aXRlJ1xuaW1wb3J0IHJlYWN0IGZyb20gJ0B2aXRlanMvcGx1Z2luLXJlYWN0J1xuXG5leHBvcnQgZGVmYXVsdCBkZWZpbmVDb25maWcoe1xuICBwbHVnaW5zOiBbcmVhY3QoKV0sXG4gIHNlcnZlcjogeyBwb3J0OiA1MTczIH0sXG4gIGJ1aWxkOiB7XG4gICAgdGFyZ2V0OiAnZXMyMDIwJyxcbiAgICByb2xsdXBPcHRpb25zOiB7XG4gICAgICBvdXRwdXQ6IHtcbiAgICAgICAgbWFudWFsQ2h1bmtzKGlkKSB7XG4gICAgICAgICAgaWYgKGlkLmluY2x1ZGVzKCdub2RlX21vZHVsZXMvcmVhY3QnKSB8fCBpZC5pbmNsdWRlcygnbm9kZV9tb2R1bGVzL3JlYWN0LWRvbScpKSB7XG4gICAgICAgICAgICByZXR1cm4gJ3JlYWN0LXZlbmRvcidcbiAgICAgICAgICB9XG4gICAgICAgICAgaWYgKGlkLmluY2x1ZGVzKCdub2RlX21vZHVsZXMvdGhyZWUnKSB8fCBpZC5pbmNsdWRlcygnQHJlYWN0LXRocmVlJykpIHtcbiAgICAgICAgICAgIHJldHVybiAndmlld2VyLTNkJ1xuICAgICAgICAgIH1cbiAgICAgICAgICBpZiAoaWQuaW5jbHVkZXMoJ3NyYy9WaWV3ZXJDYW52YXMuanN4JykgfHwgaWQuaW5jbHVkZXMoJ3NyYy9TdGVwTW9kZWwuanN4JykgfHwgaWQuaW5jbHVkZXMoJ3NyYy9zdGVwTG9hZGVyLmpzJykpIHtcbiAgICAgICAgICAgIHJldHVybiAndmlld2VyLXJ1bnRpbWUnXG4gICAgICAgICAgfVxuICAgICAgICAgIHJldHVybiB1bmRlZmluZWRcbiAgICAgICAgfSxcbiAgICAgIH0sXG4gICAgfSxcbiAgfSxcbn0pXG4iXSwKICAibWFwcGluZ3MiOiAiO0FBQThVLFNBQVMsb0JBQW9CO0FBQzNXLE9BQU8sV0FBVztBQUVsQixJQUFPLHNCQUFRLGFBQWE7QUFBQSxFQUMxQixTQUFTLENBQUMsTUFBTSxDQUFDO0FBQUEsRUFDakIsUUFBUSxFQUFFLE1BQU0sS0FBSztBQUFBLEVBQ3JCLE9BQU87QUFBQSxJQUNMLFFBQVE7QUFBQSxJQUNSLGVBQWU7QUFBQSxNQUNiLFFBQVE7QUFBQSxRQUNOLGFBQWEsSUFBSTtBQUNmLGNBQUksR0FBRyxTQUFTLG9CQUFvQixLQUFLLEdBQUcsU0FBUyx3QkFBd0IsR0FBRztBQUM5RSxtQkFBTztBQUFBLFVBQ1Q7QUFDQSxjQUFJLEdBQUcsU0FBUyxvQkFBb0IsS0FBSyxHQUFHLFNBQVMsY0FBYyxHQUFHO0FBQ3BFLG1CQUFPO0FBQUEsVUFDVDtBQUNBLGNBQUksR0FBRyxTQUFTLHNCQUFzQixLQUFLLEdBQUcsU0FBUyxtQkFBbUIsS0FBSyxHQUFHLFNBQVMsbUJBQW1CLEdBQUc7QUFDL0csbUJBQU87QUFBQSxVQUNUO0FBQ0EsaUJBQU87QUFBQSxRQUNUO0FBQUEsTUFDRjtBQUFBLElBQ0Y7QUFBQSxFQUNGO0FBQ0YsQ0FBQzsiLAogICJuYW1lcyI6IFtdCn0K
