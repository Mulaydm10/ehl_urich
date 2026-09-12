# 17 — Phase 3: the ROUTE tab

Written 2026-09-13 ~00:40 CEST on the Mac. This is the phase that turns a
finished backend into something a judge can click.

Before this, `streamlit_app.py` had **zero references to the router**. Every
number in docs 14–16 was real and none of it was reachable from the app.

## What was added

`app/route_tab.py` (~470 lines), rendered as the **first** tab, plus four
small edits to `streamlit_app.py`: the page config, a phone stylesheet, the
import, and the tab list. The old four tabs are untouched.

It talks only to `service.py`. It never sees a DataFrame, never builds a
graph, never learns what a morton code is.

## Mobile first, because that is where it runs

The demo is served from this Mac and watched **on a phone over Tailscale**, so
the usual Streamlit habits are all wrong:

| habit | why it fails on a phone | what we did |
|---|---|---|
| controls in the sidebar | the sidebar is a hidden hamburger drawer | the Thrill Dial is in the tab body |
| `st.selectbox` of presets | a native picker wheel, two taps, no context | full-width buttons that state *why* that pair |
| `layout="wide"` | nothing to widen into; also breaks the zoom fit | `layout="centered"` — and `view_for` already assumed a 700 px canvas |
| map tiles | with the network unplugged a tile map is a black rectangle | 17,345 OSM ways drawn as grey paths, `map_provider=None` |
| a slider to explore | 20–37 ms is fast, but on 200 O-D pairs the median demand gain is −0.00° | **Cruise and Send it on one map at once** |
| fixed `height=480` px | eats a whole phone screen | 430 px, overridden to `50vh` under a 640 px media query |

## What is on the screen

**Use case A.** Both dial settings drawn on the same map — Cruise in steel
blue, Send it in gold — under `compare()`'s own headline:

> Same two points. 1.13x the distance, 83% of it on different roads,
> +2.7 deg more lean asked of you.

Then one dial in detail: the line coloured segment-by-segment by fit (dim blue
= dull for you, gold = in your flow band), red pins where the gate **refused**
a road, the summary row, and `explain()`'s sentences printed verbatim.

**Use case B.** Four start presets × {1, 1.5, 2, 3} h, one map, and the loop's
own honest label when no tour fits the budget to within 20%.

## The three traps, handled rather than hidden

1. **`fun_score` compares routes at the same dial only.** Send it legitimately
   scores below Cruise. The tab prints the dial under the metric, puts the
   whole reason in the tooltip, and shows **mean lean asked** — which is
   absolute — right beside it.
2. **Outside the box there is no answer.** The free-entry boxes are clamped to
   47.38–48.03 N, 10.72–11.96 E, and the service's refusal sentence is shown
   as an error rather than an empty map: *"We have no crowd there, so we have
   no opinion."*
3. **The dial does nothing on most pairs.** When `overlap > 0.60` and the
   demand gain is under 0.5°, the caption says so in plain words and points at
   the preset where it does work. An app that admits this is more convincing
   than one that pretends.

## A correction to doc 16

Doc 16 says *"switching rider does not change the route"*. That was measured
on the wrong pair. On **Kochel → Tegernsee** the gate genuinely bites and the
line moves a long way:

```
cell overlap between userA and bike_4e1a9d64, same points
  Cruise   z* 0.15    0.730
  Send it  z* 0.90    0.105      <- 90% different road for a different rider
refusals on that pair: userA 3, bike_da67fa06 5, bike_4e1a9d64 4
```

So the rider switch **is** demonstrable on the map — just not on the pair doc
16 tested. That preset is now labelled as the safety-and-rider demo, and the
dial demo stays on Lenggries → Bad Tölz. The doc-16 warning still holds for
the other two pairs.

## Verified by running it, not by reading it

`streamlit.testing.v1.AppTest` executes the real script and surfaces any
exception:

```
5 tabs render, 0 exceptions
27 combinations swept: 3 riders x 3 preset pairs x 3 dial settings, all clean
16 loop combinations: 4 starts x 4 durations, all render
refusal pins fire on Kochel -> Tegernsee with their reason strings
out-of-coverage start returns the refusal sentence, not a blank map
```

Then served for real and fetched from the Linux box over the tailnet:
`200 in 0.048 s`.

## A security bug the launch command introduced

`--server.address=0.0.0.0` binds **every** interface. On this network the Mac
also holds a routable public address, and Streamlit printed it:

```
External URL: http://141.70.42.255:8501
```

That is an app backed by NDA data, published to the open internet. Fixed by
`run_demo.sh`, which binds the tailnet address only:

```
TCP 100.80.210.100:8501 (LISTEN)      <- and nothing else
tailnet  200      public IP  000 (refused)
```

`--lan` and `--local` exist for fallbacks. **Never `tailscale funnel` or
`tailscale serve --funnel`** — same NDA reason, larger blast radius.

## Running it

```bash
ssh macmini
cd ~/ehl_urich/flowstate
./run_demo.sh                 # http://100.80.210.100:8501 on the phone
./run_demo.sh --lan           # conference Wi-Fi usually isolates clients;
                              # prefer the phone's hotspot with the Mac joined
```

Rebake first if the router, the cell table or the OSM layer changed:
`/Users/mulaydm10/ehl_urich/.venv/bin/python analysis/14_bake_demo.py`.
