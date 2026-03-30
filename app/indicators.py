from __future__ import annotations

import math


def safe_float(value: float | int | str) -> float:
    return float(value)


def compute_microprice_3levels(bids: list[list[str]], asks: list[list[str]]) -> float | None:
    if len(bids) < 3 or len(asks) < 3:
        return None

    numer = 0.0
    denom = 0.0
    for level in range(3):
        bid_price = safe_float(bids[level][0])
        bid_qty = safe_float(bids[level][1])
        ask_price = safe_float(asks[level][0])
        ask_qty = safe_float(asks[level][1])

        numer += ask_price * bid_qty + bid_price * ask_qty
        denom += bid_qty + ask_qty

    if denom == 0:
        return None

    return numer / denom


def compute_imbalance_3levels(bids: list[list[str]], asks: list[list[str]]) -> float | None:
    if len(bids) < 3 or len(asks) < 3:
        return None

    bid_volume = safe_float(bids[0][1]) + safe_float(bids[1][1]) + safe_float(bids[2][1])
    ask_volume = safe_float(asks[0][1]) + safe_float(asks[1][1]) + safe_float(asks[2][1])

    denom = bid_volume + ask_volume
    if denom == 0:
        return None

    return ((bid_volume - ask_volume) / denom) / 100


def compute_ob_volatility_index_3levels(
    bids: list[list[str]],
    asks: list[list[str]],
    prev_net: float | None,
) -> tuple[float | None, float | None]:
    if len(bids) < 3 or len(asks) < 3:
        return None, prev_net

    current_ask = safe_float(asks[0][1]) + safe_float(asks[1][1]) + safe_float(asks[2][1])
    current_bid = safe_float(bids[0][1]) + safe_float(bids[1][1]) + safe_float(bids[2][1])
    current_net = current_ask - current_bid

    if prev_net is None or prev_net == 0:
        return float("nan"), current_net

    ratio = current_net / prev_net
    if ratio <= 0:
        return float("nan"), current_net

    return math.log(ratio), current_net


def compute_optimal_price(microprice: float | None, imbalance: float | None) -> float | None:
    if microprice is None or imbalance is None:
        return None
    return microprice * (1.0 + imbalance)
