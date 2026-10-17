"""Council v2 (SvArbiter) regression tests — 2026-10-17.

Selected definitions are extracted from Pyfamate.py by AST and executed with host plumbing stubbed
(no engine, no GPU, no Pyfamate import side effects). Every check states the corrected behaviour.

Usage:
  python tests/test_council_v2.py            numpy-only checks
  python tests/test_council_v2.py --train    + end-to-end arbiter-train/tau/eval on synthetic rows (needs torch)
"""
import ast, contextlib, dataclasses, io, json, math, os, random, re, sys, tempfile, threading, types
from pathlib import Path

import numpy as np
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "Pyfamate.py"
tree = ast.parse(SRC.read_text(encoding="utf-8-sig"))
WANT = {
    "SvArbiter", "ArbCand", "ArbiterVerdict", "_arb_ensure_np", "_arb_pv_list", "_arb_pv_after_move",
    "_arb_scalars_for_position", "_arb_shared_and_cands", "_arb_pair_np", "_arb_boards_for_sample",
    "_arb_consensus_wr", "_arb_pair_targets", "_arb_group_key", "_arb_is_val", "_arb_offline_metrics",
    "_arb_fmt_metrics", "_arb_from_layers", "_arb_iter_jsonl", "_arb_load_for_offline", "_sv_arbiter_get",
    "sv_arbiter_train_main", "sv_arbiter_tau_main", "sv_arbiter_eval_main",
    "SvBoard", "_svboard_from_position_cmd", "sv_sq",
    "_sv_build_model", "sv_encode_planes", "sv_usi_to_label",
}
TMP = Path(tempfile.mkdtemp(prefix="council_v2_"))
mod = types.ModuleType("council_v2_extract"); sys.modules[mod.__name__] = mod
g = mod.__dict__


class _Cfg:
    arbiter_override_tau = 0.62
    arbiter_tau_gp_slope = 0.25
    arbiter_tau_gp_onset = 0.6
    arbiter_feature_tier = "scalar"
    arbiter_tier_gp_switch = 0.0


class EngineConfig:
    @classmethod
    def from_cfg(cls, cfg):
        return _Cfg()


def _count_moves(pos):
    t = str(pos).split()
    return len(t) - t.index("moves") - 1 if "moves" in t else 0


g.update(dataclasses=dataclasses, os=os, re=re, json=json, threading=threading, math=math,
         _flog=lambda *a, **k: None, _dlog=lambda *a, **k: None, _sv_arbiter_instance=None,
         _ARB_OFFLINE_CFG=None, EngineConfig=EngineConfig, _cfg={}, _count_moves=_count_moves,
         _calc_game_phase=lambda pos, cfg: min(1.5, 0.01 * _count_moves(pos)),
         _svonnx_here=lambda: str(TMP), _svonnx_export_ckpt=lambda *a, **k: None, _BASE_DIR=str(TMP), np=None)
nodes = []
for n in tree.body:
    name = getattr(n, "name", None)
    if name in WANT:
        nodes.append(n)
    elif isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and (t.id.startswith("sv_") or t.id == "_sv_HAND_MAX") for t in n.targets):
        nodes.append(n)
code = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
                  + nodes, type_ignores=[])
exec(compile(ast.fix_missing_locations(code), str(SRC), "exec"), g)
missing = WANT - set(g)
assert not missing, missing
SvArbiter, ArbCand = g["SvArbiter"], g["ArbCand"]
RESULTS = {}


def check(name, cond, detail=None):
    RESULTS[name] = bool(cond)
    print(("PASS " if cond else "FAIL ") + name + ("" if detail is None else "  %s" % (detail,)))


# 1. PV origin: candidate move is applied once.
pv_after = g["_arb_pv_after_move"]
check("pv_head_dropped", pv_after("7g7f", "7g7f 3c3d 2g2f") == ["3c3d", "2g2f"])
check("pv_without_head_kept", pv_after("7g7f", ["3c3d", "2g2f"]) == ["3c3d", "2g2f"])
B = g["_svboard_from_position_cmd"]
sample = {"sfen": "position startpos", "cands": [{"move": "7g7f", "pv": "7g7f 3c3d"}]}
root, per = g["_arb_boards_for_sample"](sample, 12)
want = B("position startpos moves 7g7f 3c3d")
leaf = per[0][2]
check("pv_leaf_equals_root_plus_pv_once",
      leaf is not None and leaf.cells == want.cells and leaf.side == want.side and per[0][3] == 1)

# 2. Override decision is winner vs NNUE, not winner vs runner-up (JUDGE-GATE counterexample).
# order: 0=nnue 1=dl 2=seed.  P(dl>seed)=0.668, P(dl>nnue)=0.45, P(nnue>seed)=0.6
pw = [[0.5, 0.55, 0.60], [0.45, 0.5, 0.668], [0.40, 0.332, 0.5]]
lg = lambda p: math.log(p / (1 - p))
score = [sum(lg(pw[i][j]) for j in range(3) if j != i) for i in range(3)]
pick, wi, p, ab = SvArbiter.decide(score, pw, 0, 0.62)
check("decide_keeps_nnue_when_it_is_winner", pick == 0, (pick, wi, round(p, 3)))
pw2 = [[0.5, 0.30, 0.6], [0.70, 0.5, 0.668], [0.4, 0.332, 0.5]]
score2 = [sum(lg(pw2[i][j]) for j in range(3) if j != i) for i in range(3)]
pick, wi, p, ab = SvArbiter.decide(score2, pw2, 0, 0.62)
check("decide_override_uses_p_vs_nnue", pick == 1 and abs(p - 0.70) < 1e-9 and not ab, (pick, p))
pick, wi, p, ab = SvArbiter.decide(score2, pw2, 0, 0.75)
check("decide_abstains_below_tau", pick == 0 and wi == 1 and ab)

# 3. Targets: 3-candidate hard label y=2 means seed beats both (old trainer taught "cand 1 wins").
tg = g["_arb_pair_targets"]({"cands": [{}, {}, {}], "y": 2, "w": 0.1})
check("hard_label_y2_three_cands", sorted(tg) == [(0, 2, 0.0, 0.1), (1, 2, 0.0, 0.1)], tg)
tg = g["_arb_pair_targets"]({"cands": [{}, {}], "wr_nn": [0.40, 0.60], "wr_dl": [0.44, 0.56], "bucket": "D"})
check("soft_target_follows_consensus_wr", len(tg) == 1 and tg[0][2] < 0.5 and tg[0][3] == 0.5, tg)
cons = g["_arb_consensus_wr"]({"cands": [{}, {}], "wr_nn": [0.4, None], "wr_dl": [0.5, 0.7]})
check("consensus_wr_mean_or_single", abs(cons[0] - 0.45) < 1e-9 and abs(cons[1] - 0.7) < 1e-9, cons)

# 4. Split by game key hash (deterministic, ≈frac), not by sorted prefix.
keys = ["start_sfens_ply24.txt/%08x" % i for i in range(4000)] + ["start_sfens_ply32.txt/%08x" % i for i in range(4000)]
iv = [g["_arb_is_val"](k, 0.1) for k in keys]
check("val_split_hash_fraction", 0.08 < sum(iv) / len(iv) < 0.12, sum(iv) / len(iv))
check("val_split_spans_sources", any(iv[:4000]) and any(iv[4000:]))
check("val_split_deterministic", iv == [g["_arb_is_val"](k, 0.1) for k in keys])


# 5. Head loading: legacy (no meta / v1 dims) rejected, v2 accepted; sources filter; OOD; tau json.
def _write_head(path, din, meta=True, sources="nnue,dl1", gp=(0.1, 0.5), seed=0):
    rng = np.random.default_rng(seed)
    d = {"s_W0": rng.normal(size=(din, 8)).astype("float32"), "s_b0": np.zeros(8, "float32"),
         "s_W1": rng.normal(size=(8, 1)).astype("float32"), "s_b1": np.zeros(1, "float32")}
    if meta:
        d.update(meta_feat_ver=np.asarray(2), meta_sources=np.asarray(sources),
                 meta_lambda=np.asarray(0.5), meta_gp_lo=np.asarray(gp[0]), meta_gp_hi=np.asarray(gp[1]))
    np.savez(path, **d)


def _fresh():
    g["_sv_arbiter_instance"] = None
    return g["_sv_arbiter_get"]()


npz = TMP / "arbiter_head.npz"
_write_head(npz, 14, meta=False)
check("legacy_v1_head_rejected", _fresh().load() is False)
_write_head(npz, 15)
arb = _fresh()
check("v2_head_loaded", arb.load() is True and arb.sources == ("nnue", "dl1") and arb.gp_range == (0.1, 0.5))
ctx = types.SimpleNamespace(cfg=_Cfg(), current_position="position startpos")
cands = [ArbCand("7g7f", "nnue", cp=30, depth=20), ArbCand("2g2f", "dl1", cp=50, depth=10),
         ArbCand("5g5f", "seed")]
sc = {"gp": 0.3, "gp_state": 0.3, "eff_s": 3.0, "ply": 30, "nnue_depth": 20, "nnue_nodes": 1e6,
      "nnue_top": "7g7f"}
v = arb.judge(ctx, cands, sc, deadline_s=1.0)
check("judge_returns_candidate_not_seed", v is not None and v.move in ("7g7f", "2g2f") and v.tier == "scalar", v)
v = arb.judge(ctx, cands, dict(sc, gp_state=1.2), deadline_s=1.0)
check("judge_out_of_gp_range_keeps_nnue", v is not None and v.move == "7g7f" and v.tier == "ood", v)
(TMP / "arbiter_tau.json").write_text(json.dumps({"Arbiter_Override_Tau": 0.9, "head_sha256": arb.head_sha}))
arb = _fresh(); arb.load()
check("tau_json_applied_for_matching_head", arb.tau == 0.9 and abs(arb.tau_eff(_Cfg(), 0.3) - 0.9) < 1e-9)
(TMP / "arbiter_tau.json").write_text(json.dumps({"Arbiter_Override_Tau": 0.9, "head_sha256": "x"}))
arb = _fresh(); arb.load()
check("tau_json_ignored_for_other_head", arb.tau is None)
os.remove(TMP / "arbiter_tau.json")

# 6. Train/serve feature parity: a labeled row and the runtime scalars give the same shared vector.
pos = "position startpos moves 7g7f 3c3d 2g2f"
row = {"sfen": pos, "eff_s": 3.0, "cands": [{"move": "8c8d", "source": "nnue", "cp": 10, "depth": 18, "nodes": 123456},
                                            {"move": "4a3b", "source": "dl1", "cp": 40, "depth": 7}]}
sh_train, _c = g["_arb_shared_and_cands"](row)
rt = g["_arb_scalars_for_position"](pos, _Cfg())
rt.update({"eff_s": 3.0, "nnue_depth": 18, "nnue_nodes": 123456})
check("train_serve_shared_features_equal", np.allclose(sh_train, SvArbiter._shared_features(rt)),
      (sh_train, SvArbiter._shared_features(rt)))
check("shared_features_not_degenerate", sh_train[2] > 0 and sh_train[3] > 0 and sh_train[4] > 0, sh_train)


# 7. End-to-end train → tau → eval on synthetic rows (torch).
def _synthetic_rows(n, seed=1):
    """Ground truth: DL's move is better iff its depth is high relative to the position phase.
    NNUE always-pick has positive regret; a learned arbiter should cut it."""
    rng = random.Random(seed)
    rows = []
    for k in range(n):
        ply = rng.randint(20, 120)
        gp = min(1.5, 0.01 * ply)
        dld = rng.randint(2, 30)
        dl_better = (dld / 30.0) > (0.3 + 0.4 * gp / 1.2)
        d = rng.uniform(0.02, 0.15)
        wr_nn_c = 0.5 - d / 2 if dl_better else 0.5 + d / 2
        wr_dl_c = 1.0 - wr_nn_c
        noise = lambda: rng.uniform(-0.01, 0.01)
        rows.append({"sfen": "position startpos", "gp_state": gp, "ply": ply, "eff_s": rng.choice([1, 3, 8]),
                     "game_id": "g%d" % (k // 3), "oracle_ver": 3, "bucket": "G",
                     "cands": [{"move": "7g7f", "source": "nnue", "cp": rng.randint(-100, 100), "depth": 20, "nodes": 10 ** 6},
                               {"move": "2g2f", "source": "dl1", "cp": rng.randint(-100, 100), "depth": dld}],
                     "wr_nn": [wr_nn_c + noise(), wr_dl_c + noise()], "wr_dl": [wr_nn_c + noise(), wr_dl_c + noise()]})
    return rows


if "--train" in sys.argv:
    os.remove(npz)
    data = TMP / "arbiter_labeled.jsonl"
    with open(data, "w", encoding="utf-8") as fh:
        for r in _synthetic_rows(3000):
            fh.write(json.dumps(r) + "\n")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        g["sv_arbiter_train_main"](["--data", str(data), "--no-trunk", "--head-epochs", "60", "--out", str(TMP / "arbiter")])
    out = buf.getvalue()
    print(out)
    with np.load(npz) as _z:
        d = {k: _z[k] for k in _z.files}
    check("train_writes_v2_meta", int(d["meta_feat_ver"]) == 2 and str(d["meta_sources"]) == "nnue,dl1"
          and d["s_W0"].shape[0] == 15)
    vline = [ln for ln in out.splitlines() if "Tier-S val" in ln][-1]
    reg = dict(x.split("=") for x in vline.split("|")[1].replace("mean WR regret:", "").split())
    check("val_regret_arbiter_below_nnue", float(reg["arbiter"]) < 0.5 * float(reg["nnue"]), reg)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        g["_sv_arbiter_instance"] = None
        g["sv_arbiter_tau_main"](["--data", str(data), "--val-only"])
    print(buf.getvalue())
    tj = json.loads((TMP / "arbiter_tau.json").read_text())
    arb = _fresh(); arb.load()
    check("tau_json_bound_to_trained_head", tj["head_sha256"] == arb.head_sha and arb.tau == tj["Arbiter_Override_Tau"])
    check("tau_regret_not_worse_than_nnue", tj["regret_arb"] <= tj["regret_nnue"], tj)

    # Tier-T smoke: random-init trunk checkpoint as --base, real positions and PVs, 1 epoch.
    import torch
    trunk = g["_sv_build_model"](ch=16, blocks=1, ver=3, in_ch=g["sv_N_PLANES"], arb=True)
    torch.save({"model": trunk.state_dict()}, TMP / "base.pt")
    rows_t = _synthetic_rows(60, seed=7)
    for r in rows_t:
        r["cands"][0]["pv"] = "7g7f 3c3d 2g2f"
        r["cands"][1]["pv"] = ["3c3d", "7g7f"]
    data_t = TMP / "arbiter_labeled_t.jsonl"
    with open(data_t, "w", encoding="utf-8") as fh:
        for r in rows_t:
            fh.write(json.dumps(r) + "\n")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        g["sv_arbiter_train_main"](["--data", str(data_t), "--base", str(TMP / "base.pt"), "--ch", "16",
                                    "--blocks", "1", "--epochs", "1", "--head-epochs", "5",
                                    "--out", str(TMP / "arbiter_t")])
    out = buf.getvalue()
    print(out)
    with np.load(npz) as _z:
        d = {k: _z[k] for k in _z.files}
    check("tier_t_head_written", "t_W0" in d and d["t_W0"].shape[0] == 19 and "Tier-T ep0" in out)
    arb = _fresh(); arb.load()
    check("tier_t_head_loadable", arb._head_t is not None and arb.lam == 0.5)

bad = [k for k, ok in RESULTS.items() if not ok]
print("%d/%d PASS" % (len(RESULTS) - len(bad), len(RESULTS)))
sys.exit(1 if bad else 0)
