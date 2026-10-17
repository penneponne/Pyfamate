# Pyfamate: ideas parked by the 2026-10-17 dedup

On 2026-10-17, 22 top-level definitions were removed from `Pyfamate.py`, and one more (`_opponent_id_set_pending`) was restored and reconnected. Nothing in the file referenced them: no name and no string mentioned them, and `--selftest-connectivity` lists them as unused. The ideas behind them are recorded here so they are not lost.

Each "code" link goes to the last commit that still contains the definition. It is [`fd1590e`](https://github.com/yfamate/Pyfamate/blob/fd1590e/Pyfamate.py).

To bring an idea back, restore the definition from that commit, then connect it to a caller.

## Ideas worth trying again

| idea | what it does | why it is interesting | code |
|---|---|---|---|
| **Second ponder slot driven by disagreement** (`_multi_ponder_alt_reply`, SMP v6.2) | Takes DL_1's predicted reply from its PV. If that reply differs from NNUE's ponder reply, it uses it as an alternative ponder line. A fallback borrows the reply from another root move's PV. | Ponder budget goes to positions where the engines disagree about the opponent's reply. Those are the positions where a single ponder line misses most. | [L18034](https://github.com/yfamate/Pyfamate/blob/fd1590e/Pyfamate.py#L18034) |
| **Ponder move from the winning engine's PV** (`_override_ponder_core`, OVR-PONDER) | When the council plays a move other than NNUE's, the ponder move is taken from the PV of the engine that won the vote. | Once this was disconnected, `bestmove D ponder P` carried NNUE's reply to a different move. The audit fix `_u_align_ponder` re-implements the same contract. | [L18080](https://github.com/yfamate/Pyfamate/blob/fd1590e/Pyfamate.py#L18080) |
| **DL PV-overlap confidence boost** (`_calc_dl_pv_overlap_boost`) | When DL's top 3 moves all expect the same opponent reply, the DL vote weight goes up, from ×1.0 to ×1.10. | It is a confidence signal that search depth alone does not give. It could be a feature of the learned arbiter (Council v2). | [L16627](https://github.com/yfamate/Pyfamate/blob/fd1590e/Pyfamate.py#L16627) |
| **Opponent style identification by disagreement sampling** (`_opponent_id_set_pending`) — **restored and reconnected in this PR** (it was a bug: the observer kept consuming pending samples that nothing wrote) | Stores the NNUE-style and DL-style predictions of the opponent's next move, but only when they disagree. The opponent's real move then shows which kind of engine it is. It stops once the opponent is identified, either by name or manually. | It identifies the opponent online from the opponent's own moves. The observing half (`_opponent_id_observe`) is still connected. Only the sampling half was orphaned, so it is worth checking whether OPP-ID still receives samples. | [L22289](https://github.com/yfamate/Pyfamate/blob/fd1590e/Pyfamate.py#L22289) |
| **詰めろ / n手すき queries** (`_zyfamate_tsumero`, `_zyfamate_tesuki`, `_zf_parse_tesuki_lines`) | Wrappers that ask the resident Zyfamate server about threats: whether a move is 詰めろ, and n手すき for n ≤ 3. | They measure threats, not only proofs. That makes them inputs for Sharpness (playing 紛れ when behind) and the tonshi guard. | [L25861](https://github.com/yfamate/Pyfamate/blob/fd1590e/Pyfamate.py#L25861) |
| **Second book, warm start** (`_book2_fire`, `_book2_fire_async`, `_book2_probe_seed_if_ready`) | When the main book runs out, a second book engine starts in the background. If it is ready before this move's vote, it joins as an advisory seed, with a probe that does not consume it. | It extends book coverage without blocking. It was turned off by `[BOOK2-OFF 2026-07-11]`. | [L14893](https://github.com/yfamate/Pyfamate/blob/fd1590e/Pyfamate.py#L14893) |
| **Vision model as a third opinion** (`_model_wr_for_position`) | Gets the board-vision model's win rate for any position command. | It gives an independent value estimate, separate from both NNUE and DL. | [L1310](https://github.com/yfamate/Pyfamate/blob/fd1590e/Pyfamate.py#L1310) |
| **Floor on the DL vote weight, tied to game phase** (`_apply_weight_floor`, `_calc_weight_floor_gp`) | Sets a minimum DL vote weight that moves with game phase. | This belongs to the old weighted vote, which SvArbiter has replaced. It is kept as history of the design. | [L15968](https://github.com/yfamate/Pyfamate/blob/fd1590e/Pyfamate.py#L15968) |

## Removed as plain leftovers

| definition | why it was removed |
|---|---|
| `_lc_fallback_move_core` | The Light Council fallback core. The Light Council lane is gone. |
| `_sr_linger_lines` | A compatibility shim for an old API. `_sr_linger_split` is used directly. |
| `_game_phase_fit_value` | A duplicate of the vectorised GP fit path. |
| `sv_label_to_usi`, `sv_policy_mask`, `sv_load_games` | Vision-model helpers that nothing calls. `cyfnet.py` has its own port of `sv_label_to_usi`. |
| `_arb_kif_root`, `_arb_list_kif`, `_arb_kif_positions` | The kif replay source of `arbiter-synth`. The 2026-07-17 user decision replaced it with start-position sets. |
| 8 constants (`_COUNCIL_WEIGHT_FLOOR`, `_REGIME_*_SCALE/BOOST`, `_SCORE_CLAMP_CP`, `_WINRATE_EPSILON`, `_DL_ENGINE_BASENAME`, `_SV_GP_HAND_W`, `_mon_gpu_util_raw`) | Nothing reads them. |
