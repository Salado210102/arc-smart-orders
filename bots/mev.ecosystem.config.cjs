// PM2 process file for the MEV monitors:  pm2 start bots/mev.ecosystem.config.cjs
//
// They run in MONITOR-ONLY mode unless `KEEPER_PK` is set in bots/.env (safe: no capital at risk).
// Fill the addresses in bots/.env first, or the bots will log "ERROR: set …" and idle.
//
// cwd = repo root so the scripts' `load_env("bots/.env")` resolves.
module.exports = {
  apps: [
    {
      name: "mev-liquidations",
      cwd: __dirname + "/..",
      script: "bots/liquidation_monitor.py",
      interpreter: "python3",
      autorestart: true,
      max_restarts: 100,
      restart_delay: 5000,
      time: true,
      out_file: "logs/mev-liquidations.out.log",
      error_file: "logs/mev-liquidations.err.log",
    },
    {
      name: "mev-oracle-arb",
      cwd: __dirname + "/..",
      script: "bots/oracle_arb_monitor.py",
      interpreter: "python3",
      autorestart: true,
      max_restarts: 100,
      restart_delay: 5000,
      time: true,
      out_file: "logs/mev-oracle-arb.out.log",
      error_file: "logs/mev-oracle-arb.err.log",
    },
    {
      name: "mev-jit",
      cwd: __dirname + "/..",
      script: "bots/jit_liquidity_monitor.py",
      interpreter: "python3",
      autorestart: true,
      max_restarts: 100,
      restart_delay: 5000,
      time: true,
      out_file: "logs/mev-jit.out.log",
      error_file: "logs/mev-jit.err.log",
    },
    {
      name: "mev-morpho",
      cwd: __dirname + "/..",
      script: "bots/mev_morpho_liquidator.py",
      interpreter: "python3",
      autorestart: true,
      max_restarts: 100,
      restart_delay: 5000,
      time: true,
      out_file: "logs/mev-morpho.out.log",
      error_file: "logs/mev-morpho.err.log",
    },
  ],
};
