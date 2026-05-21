// pm2 process config — run with: pm2 start ecosystem.config.js
// Install pm2: npm i -g pm2
// Auto-start on reboot: pm2 startup && pm2 save

module.exports = {
  apps: [
    {
      name: "api",
      script: "uv",
      args: "run uvicorn concert_finder_api.main:app --host 0.0.0.0 --port 8000",
      cwd: "./apps/api",
      interpreter: "none",
      env: { NODE_ENV: "production" },
      watch: false,
    },
    {
      name: "web",
      script: "pnpm",
      args: "start",
      cwd: "./apps/web",
      interpreter: "none",
      env: { NODE_ENV: "production", PORT: "3000" },
      watch: false,
    },
    {
      name: "worker",
      script: "uv",
      args: "run python worker.py",
      cwd: "./worker",
      interpreter: "none",
      watch: false,
      autorestart: true,
      restart_delay: 60000,
    },
  ],
};
