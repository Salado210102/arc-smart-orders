// PM2 process file for the launchpad alerts bot:  pm2 start ops/launchpad-alerts.ecosystem.config.cjs
module.exports = {
  apps: [
    {
      name: "arc-alerts",
      cwd: __dirname + "/..",
      script: "ops/launchpad-alerts.mjs",
      interpreter: "node",
      autorestart: true,
      max_restarts: 100,
      restart_delay: 5000,
      time: true,
      out_file: "logs/arc-alerts.out.log",
      error_file: "logs/arc-alerts.err.log",
    },
  ],
};
