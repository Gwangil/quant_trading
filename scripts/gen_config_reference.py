"""config.py 의 dataclass 필드·기본값·주석으로 docs/06_config_reference.md 를 생성한다.
사용: python scripts/gen_config_reference.py   (config.py 를 바꾸면 다시 실행)"""
import re, pathlib

SRC = pathlib.Path("src/qtrade/config.py").read_text(encoding="utf-8")
OUT = pathlib.Path("docs/06_config_reference.md")
SECTION = {"StrategyConfig": "최상위", "DataConfig": "data", "SyntheticConfig": "data.synthetic", "BasketConfig": "baskets",
           "EntryConfig": "entry", "ExitConfig": "exit", "RegimeConfig": "regime", "RiskConfig": "risk", "CostConfig": "costs"}
STATUS = {  # 프로필에서 쓰지 않는 실험 옵션
    "budget_frac": "실험", "first_slice_dip_pct": "실험", "first_slice_mult": "실험", "depth_boost": "기각(MDD 악화)",
    "addon_below_avg_pct": "실험(v5 재현용)", "lot_tp_sell_frac": "기각(MDD 악화)", "upday_min_rise": "실험", "basket_sl_pct": "기각(해로움)",
    "soft_exit_pnl_pct": "실험", "bear_no_new_lots": "실험", "ref_vol_bear_abs": "기각(효과 없음)", "ref_vol_bear_rel": "기각(효과 없음)",
    "breaker_dd": "공격형만", "max_vol_to_open": "실험", "vol_target_annual": "기각(개선 없음)", "max_exposure": "실험",
    "dd_scale_start": "기각(회복 지연)", "dd_scale_floor": "기각", "dd_scale_min_mult": "기각", "integer_shares": "검토용", "slippage_pct": "실측 후 설정",
    "synthetic": "프록시용", "backfill": "프록시용", "budget_mode": "비교용(fixed)",
}
blocks = re.findall(r"@dataclass\nclass (\w+):\n(.*?)(?=\n\n\n|\n@dataclass|\n_NESTED)", SRC, flags=re.S)
lines = ["# 06. 설정 레퍼런스 (자동 생성: `python scripts/gen_config_reference.py`)", "",
         "YAML 은 `qtrade make-configs` 가 `src/qtrade/profiles.py` 에서 생성한다. 기본값은 **균형형 프로필과 같다**(테스트로 강제).",
         "상태: (비어 있음) = 프로필 코어에서 사용 · 실험 = 코드는 있으나 프로필에서 미사용 · 기각 = 실데이터에서 불리해 끔(근거 docs/02 §3).", ""]
for cls, body in blocks:
    lines += [f"## `{SECTION.get(cls, cls)}` ({cls})", "", "| 키 | 기본값 | 의미 | 상태 |", "|---|---|---|---|"]
    for line in body.splitlines():
        m = re.match(r"\s{4}(\w+):\s*([^=]+?)\s*=\s*(.+?)(?:\s{2,}#\s*(.*))?$", line)
        if not m or line.strip().startswith(("def ", "#", '"')):
            continue
        f, _t, default, comment = m.groups()
        if default.startswith("field("):
            default = "(하위 섹션)"
        lines.append(f"| `{f}` | `{default.strip()}` | {(comment or '').strip()} | {STATUS.get(f, '')} |")
    lines.append("")
lines += ["## 점 표기 오버라이드", "", "탐색 그리드와 `with_overrides` 는 `섹션.키` 형태를 쓴다. 예: `exit.upday_sell_frac: 0.2`, `regime.breaker_dd: 0.25`.", ""]
OUT.write_text("\n".join(lines), encoding="utf-8")
print("wrote", OUT)
