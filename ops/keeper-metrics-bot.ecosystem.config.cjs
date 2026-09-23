// PM2 process file for the keeper metrics bot (24/7):
//   cd /var/www/arc-keeper && pm2 start ops/keeper-metrics-bot.ecosystem.config.cjs
//   pm2 save
//
// Runs in `daemon` mode: periodic Telegram push (every METRICS_MS) + on-demand `/metrics` replies.
// Reuses the SAME bot token as arc-alerts via ops/launchpad-alerts.env (override with METRICS_ENV).
module.exports = {
  apps: [
    {
      name: "arc-metrics",
      cwd: __dirname + "/..",
      script: "ops/keeper-metrics-bot.mjs",
      args: "daemon",
      interpreter: "node",
      autorestart: true,
      max_restarts: 100,
      restart_delay: 5000,
      time: true,
      out_file: "logs/arc-metrics.out.log",
      error_file: "logs/arc-metrics.err.log",
    },
  ],
};
