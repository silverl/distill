import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
	plugins: [react(), tailwindcss()],
	server: {
		port: 5173,
		proxy: {
			"/api": {
				target: "http://localhost:4321",
				changeOrigin: true,
			},
		},
	},
	resolve: {
		alias: {
			"@shared": new URL("./shared", import.meta.url).pathname,
			"@": new URL("./src", import.meta.url).pathname,
		},
	},
});
