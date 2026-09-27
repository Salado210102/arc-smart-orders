import unittest

from indexer.pnl import (
    leg_from_swap, reconstruct_legs, closed_trades, wallet_pnl, entry_timing_percentiles,
    coordinated_clusters, _mark_open,
)
from indexer.tokenmeta import USD_STABLES

USDC = "0x3600000000000000000000000000000000000000"
TOK = "0x00000000000000000000000000000000000000aa"
POOL = "0xpool"
POOLS = {POOL: (TOK, USDC)}  # currency0 = token, currency1 = USDC


def swap(block, a0, a1, wallet="0xw", log=0, pool=POOL):
    return {"wallet": wallet, "pool": pool, "block_number": block, "log_index": log,
            "amount_in": str(a0), "amount_out": str(a1)}


class PnlTests(unittest.TestCase):
    def test_leg_from_swap_buy_and_sell(self):
        buy = leg_from_swap(swap(1, -100 * 10**18, 1_000_000), POOLS)
        self.assertEqual(buy["side"], "buy")
        self.assertAlmostEqual(buy["token_qty"], 100.0)
        self.assertAlmostEqual(buy["stable_value"], 1.0)
        sell = leg_from_swap(swap(2, 100 * 10**18, -2_000_000), POOLS)
        self.assertEqual(sell["side"], "sell")
        self.assertAlmostEqual(sell["stable_value"], 2.0)

    def test_leg_from_swap_reversed_orientation(self):
        pools = {POOL: (USDC, TOK)}
        buy = leg_from_swap(swap(1, 1_000_000, -100 * 10**18), pools)
        self.assertEqual(buy["side"], "buy")
        self.assertAlmostEqual(buy["stable_value"], 1.0)
        self.assertAlmostEqual(buy["token_qty"], 100.0)

    def test_reconstruct_skips_non_stable_pools(self):
        pools = {POOL: ("0xtokA", "0xtokB")}
        legs, skipped = reconstruct_legs([swap(1, -1, 1)], pools)
        self.assertEqual(legs, [])
        self.assertEqual(skipped, 1)

    def test_reconstruct_skips_stable_vs_stable(self):
        eurc = "0xbef5f6d51cb62b58e6a8f77868681825c6fe21c1"
        pools = {POOL: (USDC, eurc)}
        legs, skipped = reconstruct_legs([swap(1, -1_000_000, 1_020_000)], pools)
        self.assertEqual(legs, [])
        self.assertEqual(skipped, 1)

    def test_closed_trade_win(self):
        legs = reconstruct_legs([swap(1, -100 * 10**18, 1_000_000),
                                 swap(5, 100 * 10**18, -2_000_000)], POOLS)[0]
        trades = closed_trades(legs)
        self.assertEqual(len(trades), 1)
        t = trades[0]
        self.assertAlmostEqual(t.realized, 1.0)
        self.assertAlmostEqual(t.exit_multiple, 2.0)
        self.assertEqual(t.entry_block, 1)
        self.assertEqual(t.exit_block, 5)

    def test_closed_trade_loss_and_partial(self):
        legs = reconstruct_legs([swap(1, -100 * 10**18, 2_000_000),
                                 swap(2, 50 * 10**18, -500_000)], POOLS)[0]
        trades = closed_trades(legs)
        self.assertEqual(len(trades), 1)
        self.assertAlmostEqual(trades[0].realized, -0.5)
        self.assertAlmostEqual(trades[0].exit_multiple, 0.5)

    def test_wallet_pnl_aggregates(self):
        legs = reconstruct_legs([swap(1, -100 * 10**18, 1_000_000),
                                 swap(5, 100 * 10**18, -2_000_000),
                                 swap(1, -100 * 10**18, 2_000_000, wallet="0xw2"),
                                 swap(5, 100 * 10**18, -1_000_000, wallet="0xw2")], POOLS)[0]
        stats = wallet_pnl(closed_trades(legs), min_trades=1)
        self.assertEqual(stats["0xw"].win_rate, 1.0)
        self.assertAlmostEqual(stats["0xw"].realized_pnl, 1.0)
        self.assertEqual(stats["0xw2"].wins, 0)
        self.assertAlmostEqual(stats["0xw2"].realized_pnl, -1.0)
        self.assertEqual(stats["0xw"].confidence, "ok")
        stats8 = wallet_pnl(closed_trades(legs), min_trades=8)
        self.assertEqual(stats8["0xw"].confidence, "insuficiente")

    def test_entry_timing_percentiles(self):
        legs = reconstruct_legs([
            swap(100, -100 * 10**18, 1_000_000, wallet="0xearly"),
            swap(100, 100 * 10**18, -2_000_000, wallet="0xearly"),
            swap(200, -100 * 10**18, 1_000_000, wallet="0xlate"),
            swap(200, 100 * 10**18, -2_000_000, wallet="0xlate"),
        ], POOLS)[0]
        pct = entry_timing_percentiles(closed_trades(legs))
        self.assertAlmostEqual(pct["0xearly"], 1.0)
        self.assertAlmostEqual(pct["0xlate"], 0.5)

    def test_coordinated_clusters_same_block(self):
        fb = {("0xtok", f"0xw{i}"): 100 for i in range(5)}
        fb[("0xtok", "0xloner")] = 200
        cl = coordinated_clusters(fb, min_wallets=5)
        self.assertEqual(len(cl), 5)
        self.assertEqual(len(set(cl.values())), 1)
        self.assertNotIn("0xloner", cl)

    def test_coordinated_clusters_below_threshold(self):
        fb = {("0xtok", f"0xw{i}"): 100 for i in range(4)}
        self.assertEqual(coordinated_clusters(fb, min_wallets=5), {})

    def test_left_censored_sell_is_ignored(self):
        legs = reconstruct_legs([swap(5, 100 * 10**18, -2_000_000)], POOLS)[0]
        self.assertEqual(closed_trades(legs), [])

    def test_mark_open_positions(self):
        agg = {}
        counts = {"open_positions": 0}
        positions = {"0xw": [100.0, 1.0, 5]}  # qty=100, cost=1.0, entry block 5
        _mark_open(positions, 0.02, agg, counts)  # value 2.0 -> unrealized +1.0
        self.assertAlmostEqual(agg["0xw"][7], 1.0)
        self.assertEqual(agg["0xw"][8], 1)
        self.assertEqual(counts["open_positions"], 1)
        agg2 = {}
        _mark_open(positions, None, agg2, counts)
        self.assertEqual(agg2, {})


if __name__ == "__main__":
    unittest.main()
