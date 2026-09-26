"""Exchange admission must not use the strategy's delayed delivered book."""
import numpy as np
import pandas as pd
import pytest

from models.backtest_tick import simulate_tick
from models.tick_data_types import HistoricalBBOData, HistoricalExchangeBookEvent

BASE = 1_700_000_000_000


def replay_activation(side, delivered_cross, exchange_cross):
    def prices(cross):
        return ((99.8, 100.0 if cross else 100.2) if side == "BUY"
                else (100.2 if cross else 100.0, 100.4))
    bid, ask = prices(delivered_cross)
    ebid, eask = prices(exchange_cross)
    bbo = HistoricalBBOData(
        ts_ms=np.array([BASE + 100, BASE + 2000]),
        best_bid=np.array([bid, bid]), best_ask=np.array([ask, ask]),
        bid_qty=np.ones(2), ask_qty=np.ones(2), source="public_delivered_depth")
    events = [HistoricalExchangeBookEvent(
        market_id="binance_futures:perpetual:BTCUSDC", event_type="snapshot",
        exchange_ts_ns=(BASE + 100) * 1_000_000, local_receive_ts_ns=0,
        levels=(("bid", round(ebid * 10), 1.), ("ask", round(eask * 10), 1.)),
        sequence_scope="provider_ordered", source_ordinal=1)]
    params = dict(
        eta_inventory=.01, a_spread=.01, risk_per_order=.01,
        inventory_reference_qty=1., execution_intensity_slope=1., risk_horizon_s=1.,
        trade_intensity_acceleration_spread_mult=2., order_size=.001,
        max_inventory=.01, maker_fee=0., taker_fee=0., tick_size=.1, lot_size=.001,
        use_bar_pricing=True, replay_event_clock="merged", replay_clock_interval_ms=1000,
        requote_interval=100., rq_min=100., rq_max=100., collect_curves=False,
        position_timeout=0., markout_ema_span_fills=0, max_exec_book_age_s=0.,
        new_order_latency_ms=100, exchange_book_queue_mode="diagnostic",
        trace_quotes_max=100, trace_local_order_lifecycle_max=100,
        initial_live_state={"active_orders": [dict(
            side=side, price=100.1, quantity=.001, remaining=.001,
            submit_ts_ms=BASE + 100, event_ts_ms=BASE + 300,
            status="PENDING_NEW", mid_at_quote=100.1)]})
    trades = pd.DataFrame(dict(
        transact_time=np.array([BASE + 200, BASE + 1200, BASE + 2200]),
        price=np.full(3, 100.1), quantity=np.zeros(3), is_buyer_maker=np.ones(3)))
    return simulate_tick(trades, np.array([BASE]), np.array([1.]), params,
                         bbo_data=bbo, exchange_book_event_tape=events)


@pytest.mark.parametrize("side", ["BUY", "SELL"])
@pytest.mark.parametrize("delivered_cross,exchange_cross", [(False, True), (True, False)])
def test_activation_uses_execution_book_not_delivered_book(side, delivered_cross, exchange_cross):
    result = replay_activation(side, delivered_cross, exchange_cross)
    assert result["gtx_rejects"] == int(exchange_cross)
    restored = [r for r in result["_quote_trace"] if r["order_id"] == 0]
    assert bool(restored) == (not exchange_cross)
