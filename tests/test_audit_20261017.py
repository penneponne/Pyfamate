"""Regression checks for the 2026-10-17 Pyfamate audit fixes.

AST-extracts the touched definitions from Pyfamate.py and runs them with stubs
(no engines, no GPU). Every check states the corrected behaviour.
Usage: python tests/test_audit_20261017.py
"""
import ast, collections, dataclasses, enum, json, math, os, queue, re, sys, threading, time, types
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "Pyfamate.py"
tree = ast.parse(SRC.read_text(encoding="utf-8-sig"))
WANT = {"_mate_ply", "_mate_sign_score", "_parse_usi_line", "UsiLine", "_usi_is", "_dead_end_piece",
        "ShogiBoard", "_dl_conviction_mate_core", "MoveBudget", "_move_budget_left_s",
        "_drain_until_outstanding", "_u_align_ponder", "_arb_pv_list", "_arb_pv_after_move",
        "_check_council_stale", "_clamp", "_clamp01", "_sprt_sennichite_verdict_core", "_DlInfoAcc", "_mb_parse_num", "_makebook_load_blunder_seeds", "_makebook_load_seed_jsonl"}
ASSIGN = {"_RE_MATE", "_MATE_CP", "_USI_TERMINATORS", "_RE_SETOPTION"}
g = {}
g.update(dataclasses=dataclasses, enum=enum, os=os, re=re, json=json, math=math, queue=queue, sys=sys,
         threading=threading, time=time, collections=collections, namedtuple=collections.namedtuple,
         _flog=lambda *a, **k: None, _dlog=lambda *a, **k: None, _move_overhead_s=0.1,
         _move_overhead_ms=100, _ZOBRIST_VERIFY=False)
nodes = []
_seg = ast.get_source_segment
_src = SRC.read_text(encoding="utf-8-sig")
for n in tree.body:
    if isinstance(n, (ast.Import, ast.Assign, ast.For, ast.AnnAssign)) and (
            "_zb" in (_seg(_src, n) or "") or "_ZB_" in (_seg(_src, n) or "")):
        nodes.append(n)   # Zobrist tables used by ShogiBoard
    elif getattr(n, "name", None) in WANT:
        nodes.append(n)
    elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and (t.id in ASSIGN or t.id.startswith("_RE_"))
                                           for t in n.targets):
        nodes.append(n)
code = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
                  + nodes, type_ignores=[])
exec(compile(ast.fix_missing_locations(code), str(SRC), "exec"), g)
missing = WANT - set(g)
assert not missing, missing
R = {}


def check(name, cond, detail=None):
    R[name] = bool(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if detail is None else "  %r" % (detail,)))


# 1. mate score forms: `mate +`, `mate -`, `mate +5`, `mate -3`.
P = g["_parse_usi_line"]
for txt, want in (("info depth 9 score mate + pv 2b8h+", 1), ("info depth 9 score mate - pv 8h2b", -1),
                  ("info depth 9 score mate +5 pv 2b8h+", 5), ("info depth 9 score mate -3 pv 1a1b", -3)):
    check("mate_parse " + txt.split("score ")[1].split(" pv")[0], P(txt).mate == want, P(txt).mate)

# 2. legality: self-check from a non-check position (pinned piece) and dead-end pieces.
SB = g["ShogiBoard"]
b2 = SB(sfen="sfen 4r4/9/9/9/9/9/9/4G4/3K5 b - 1")
check("sanity_not_in_check", not b2._is_king_attacked(b2.side))
b3 = SB(sfen="sfen 3kr4/9/9/9/9/9/9/4G4/4K4 b - 1")
check("pinned_gold_sideways_is_illegal", b3.illegal_drop_reason("5h4h") == "in_check", b3.illegal_drop_reason("5h4h"))
check("pinned_gold_forward_is_legal", b3.illegal_drop_reason("5h5g") is None, b3.illegal_drop_reason("5h5g"))
b4 = SB(sfen="sfen 4k4/9/9/9/9/9/9/9/4K4 b PLN 1")
check("drop_pawn_last_rank_illegal", b4.illegal_drop_reason("P*1a") == "dead_end")
check("drop_knight_second_rank_illegal", b4.illegal_drop_reason("N*1b") == "dead_end")
check("drop_knight_third_rank_legal", b4.illegal_drop_reason("N*1c") is None)
b5 = SB(sfen="sfen 4k4/8P/9/9/9/9/9/9/4K4 b - 1")
check("pawn_to_last_rank_without_promotion_illegal", b5.illegal_drop_reason("1b1a") == "dead_end")
check("pawn_to_last_rank_with_promotion_legal", b5.illegal_drop_reason("1b1a+") is None)

# 3. conviction-mate never overrides a declaration.
C = g["_dl_conviction_mate_core"]
check("conviction_mate_keeps_win", C(False, "2b3c", "win", True, None) is False)
check("conviction_mate_still_fires", C(False, "2b3c", "7g7f", True, None) is True)

# 4. MoveBudget.left_s counts byoyomi.
MB = g["MoveBudget"]
mb = MB(eff_s=9.6, remaining_ms=400, t0=time.perf_counter(), byo_ms=10000)
check("left_s_includes_byoyomi", mb.left_s() > 5.0, round(mb.left_s(), 2))


# 5. stale bestmove drain by go/bestmove counts.
class FakeEng:
    def __init__(self, lines, go_sent, bm_seen):
        self._q = queue.Queue()
        for ln in lines:
            self._q.put(ln)
        self._go_sent, self._bm_seen, self.sent = go_sent, bm_seen, []

    def send(self, s):
        self.sent.append(s)

    def _note_line(self, ln):
        if ln is not None and ln.startswith("bestmove"):
            self._bm_seen += 1
        return ln


e = FakeEng(["info depth 3 pv 7g7f", "bestmove 7g7f", "info depth 1 pv 2g2f"], go_sent=2, bm_seen=0)
ok = g["_drain_until_outstanding"](e, 1, 0.5, "t", send_stop=False)
check("drain_keeps_latest_go", ok and e._go_sent - e._bm_seen == 1 and e._q.get_nowait() == "info depth 1 pv 2g2f")
e = FakeEng([], go_sent=3, bm_seen=3)
check("drain_noop_when_caught_up", g["_drain_until_outstanding"](e, 0, 0.1, "t") and e.sent == [])

# 6. ponder aligned with an overridden verdict.
st = types.SimpleNamespace(verdict="2g2f", nnue_top="7g7f", dl_top="2g2f", pv_mate_override=False,
                           ponder_move="3c3d", dl1_pv_lines={"2g2f": ["2g2f", "8c8d", "2f2e"]})
g["_u_align_ponder"](st)
check("ponder_follows_dl_pv_after_override", st.ponder_move == "8c8d", st.ponder_move)
st = types.SimpleNamespace(verdict="5g5f", nnue_top="7g7f", dl_top="2g2f", pv_mate_override=False,
                           ponder_move="3c3d", dl1_pv_lines={})
g["_u_align_ponder"](st)
check("ponder_dropped_for_other_override", st.ponder_move is None)
st = types.SimpleNamespace(verdict="7g7f", nnue_top="7g7f", dl_top="2g2f", pv_mate_override=False,
                           ponder_move="3c3d", dl1_pv_lines={})
g["_u_align_ponder"](st)
check("ponder_kept_when_nnue_move_played", st.ponder_move == "3c3d")

# 7. stale-exempt reads the record key that exists and tolerates None gap_min.
cfg = types.SimpleNamespace(council_sanity_enable=True, council_sanity_window=2)
ctx = types.SimpleNamespace(cfg=cfg, game_log=[{"council_winner": "7g7f"},
                                               {"council_winner": "7g7f", "score_gap_dl_nnue": 400,
                                                "dl_gap_min_used": None}])
check("stale_exempt_uses_score_gap_dl_nnue", g["_check_council_stale"](ctx, "7g7f") is False)

# 8. setoption with an empty value parses.
m = g["_RE_SETOPTION"].match("setoption name OppID_DL_Names value")
check("setoption_empty_value_parses", m is not None and m.group(2) == "", m and m.groups())
m = g["_RE_SETOPTION"].match("setoption name USI_Hash value 1024")
check("setoption_value_parses", m.group(1) == "USI_Hash" and m.group(2) == "1024")

# 9. perpetual check: all of our moves in the cycle were checks -> refuse; a cycle with one quiet move -> not perpetual.
cyc = "2i1i 1a2a 1i2i 2a1a " * 3
bp = SB(sfen="sfen 8k/9/9/9/9/9/9/9/4K2R1 b - 1 moves " + cyc.strip())
check("perpetual_check_detected", bp.is_perpetual_check_move("2i1i") is True)
bq = bp.clone()
bq._hist_check[len(bq._hist_check) - 4] = False   # pretend one of our moves in the cycle was quiet
check("plain_repetition_completed_by_check_not_perpetual", bq.is_perpetual_check_move("2i1i") is False)

# 10. dedup helpers keep behaviour.
acc = g["_DlInfoAcc"]()
for ln in ("info depth 5 multipv 1 score cp 120 pv 7g7f 3c3d", "info depth 9 multipv 1 score cp 80 pv 7g7f 8c8d",
           "info depth 9 multipv 2 score mate + pv 2g2f", "info depth 3 score cp 10"):
    acc.add(P(ln))
check("dl_acc_scores", acc.moves_scores == {"7g7f": 80, "2g2f": g["_MATE_CP"]}, acc.moves_scores)
check("dl_acc_deepest_pv", acc.pv_lines["7g7f"] == ["7g7f", "8c8d"] and acc.depth_best["7g7f"] == 9)
check("mb_parse_num", g["_mb_parse_num"]("x", 5) == 5 and g["_mb_parse_num"](" 2.5 ", 0, to_int=False, hi=2.0) == 2.0)

bad = [k for k, v in R.items() if not v]
print("%d/%d PASS" % (len(R) - len(bad), len(R)))
sys.exit(1 if bad else 0)
