# 31 — The rider's own mode

A rider asks for a kind of difficulty, not a preset. "Corner after corner, up
in the passes, on roads nobody rides" is a weight vector over the cell table;
it is simply not one of the four the mode scan named.

So the router now accepts one:

    mode = "custom:reversals_km=+2,elev_mean=+1,n_rides=-1"

Everything else is unchanged. The spec is parsed in `modes.custom_columns`,
goes through the same `mode_preference` percentile ranks and the same
`mode_penalty` bounded by `MODE_ALPHA`, and is a deterministic string so it
still keys the graph cache in `service._graph`.

Three limits are in the parser rather than in the UI, because the UI is not
the only caller:

* only columns that appear in a named mode may be used — the ones doc 21
  passed. `demand_p90` is not among them: the thrill dial *is* the demand
  axis, and weighting demand again would count it twice.
* weight in [-2, 2], non-zero, at most four columns.
* an unparseable spec raises. Nothing silently degrades to `flow`.

The mode never touches `flow` and never touches the gate. A rider who answers
"as hard as possible" moves the dial; roads past `skill + 2σ` stay deleted.

## What the app asks, and what it does not

`app/src/domain/ridePreference.ts` holds the mapping from five questions to
the spec above: how hard (dial), how many corners (`reversals_km`), how high
(`elev_mean`), how busy (`n_rides`), scenic or a challenge
(`elev_prominence_m` / `rhythm_purity`).

Three things riders ask for that are not offered, and the reason is shown in
the app rather than silently approximated:

* left-hand vs right-hand corners — the cell table counts reversals per km,
  not the side of each one.
* climb separately from descent — elevation is a per-cell mean and prominence,
  not a signed grade along the direction of travel.
* gravel on purpose — unpaved is a ×0.55 penalty in the fit score; inverting a
  penalty into a preference needs data the crowd set does not carry.
