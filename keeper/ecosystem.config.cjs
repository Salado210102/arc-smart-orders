// PM2 process file:  pm2 start ecosystem.config.cjs && pm2 save
module.exports = {
  apps: [
    {
      name: "arc-keeper",
      cwd: __dirname,
      script: "npm",
      args: "start",
      autorestart: true,
      max_restarts: 100,
      restart_delay: 5000,
      time: true,
      out_file: "logs/keeper.out.log",
      error_file: "logs/keeper.err.log",
    },
  ],
};
